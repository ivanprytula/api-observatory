"""Tests for source probe and contract snapshot job handlers.

Coverage:
- run_source_probe: health check probing, circuit breaker, error handling
- run_source_contract_snapshot: fetch + drift detection, error paths
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from libs.platform.circuit_breaker import CircuitBreaker, CircuitOpenError
from services.ingestor.jobs import run_source_contract_snapshot, run_source_probe
from services.ingestor.models import ContractSnapshot, DriftEvent, SourceProfile


pytestmark = pytest.mark.integration


def _make_profile(
    source_id: int = 1,
    base_url: str = "https://api.example.com",
    health_check_path: str = "/health",
) -> SourceProfile:
    profile = SourceProfile(
        id=source_id,
        name=f"source-{source_id}",
        base_url=base_url,
        health_check_path=health_check_path,
        probe_interval_seconds=60,
        is_active=True,
    )
    return profile


def _mock_db_with_profile(profile: SourceProfile | None) -> AsyncMock:
    db = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = profile
    db.execute.return_value = result
    return db


def _mock_response(
    status_code: int = 200,
    content: bytes = b'{"status": "ok"}',
    json_data: dict | None = None,
) -> httpx.Response:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.content = content
    resp.json.return_value = json_data if json_data is not None else {"status": "ok"}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


# ============================================================================
# run_source_probe
# ============================================================================


class TestRunSourceProbe:
    @pytest.mark.asyncio
    async def test_skips_inactive_source(self) -> None:
        db = _mock_db_with_profile(None)

        result = await run_source_probe(db, source_id=999)

        assert result["skipped"] is True
        assert result["reason"] == "source_inactive"

    @pytest.mark.asyncio
    async def test_skips_when_circuit_open(self) -> None:
        profile = _make_profile()
        db = _mock_db_with_profile(profile)

        breaker = MagicMock(spec=CircuitBreaker)
        breaker.is_open = True

        with patch(
            "services.ingestor.jobs._get_source_probe_breaker", return_value=breaker
        ):
            result = await run_source_probe(db, source_id=1)

        assert result["skipped"] is True
        assert result["reason"] == "circuit_open"

    @pytest.mark.asyncio
    async def test_successful_probe_persists_sample(self) -> None:
        profile = _make_profile()
        db = _mock_db_with_profile(profile)
        response = _mock_response(status_code=200)

        async def _fake_call(fn):
            return await fn() if callable(fn) else fn

        mock_client = AsyncMock()
        mock_client.get.return_value = response

        with (
            patch(
                "services.ingestor.jobs._get_source_probe_breaker",
            ) as mock_breaker_fn,
            patch(
                "services.ingestor.jobs.get_http_client",
                return_value=mock_client,
            ),
            patch(
                "services.ingestor.jobs.record_health_sample",
                new_callable=AsyncMock,
            ) as mock_persist,
        ):
            breaker = MagicMock(spec=CircuitBreaker)
            breaker.is_open = False
            breaker.call = AsyncMock(return_value=response)
            mock_breaker_fn.return_value = breaker

            result = await run_source_probe(db, source_id=1)

        assert result["is_success"] is True
        assert result["status_code"] == 200
        assert result["source_id"] == 1
        assert "latency_ms" in result
        assert "response_body_hash" in result
        mock_persist.assert_called_once()

    @pytest.mark.asyncio
    async def test_failed_probe_records_error(self) -> None:
        profile = _make_profile()
        db = _mock_db_with_profile(profile)
        response = _mock_response(status_code=503)

        with (
            patch(
                "services.ingestor.jobs._get_source_probe_breaker",
            ) as mock_breaker_fn,
            patch(
                "services.ingestor.jobs.record_health_sample",
                new_callable=AsyncMock,
            ) as mock_persist,
        ):
            breaker = MagicMock(spec=CircuitBreaker)
            breaker.is_open = False
            breaker.call = AsyncMock(return_value=response)
            mock_breaker_fn.return_value = breaker

            result = await run_source_probe(db, source_id=1)

        assert result["is_success"] is False
        assert result["status_code"] == 503
        mock_persist.assert_called_once()
        sample = mock_persist.call_args[0][1]
        assert sample.is_success is False
        assert "upstream_status_503" in sample.error_message

    @pytest.mark.asyncio
    async def test_network_error_records_error_message(self) -> None:
        profile = _make_profile()
        db = _mock_db_with_profile(profile)

        with (
            patch(
                "services.ingestor.jobs._get_source_probe_breaker",
            ) as mock_breaker_fn,
            patch(
                "services.ingestor.jobs.record_health_sample",
                new_callable=AsyncMock,
            ) as mock_persist,
        ):
            breaker = MagicMock(spec=CircuitBreaker)
            breaker.is_open = False
            breaker.call = AsyncMock(
                side_effect=httpx.ConnectTimeout("connection timed out")
            )
            mock_breaker_fn.return_value = breaker

            result = await run_source_probe(db, source_id=1)

        assert result["is_success"] is False
        assert result["status_code"] is None
        mock_persist.assert_called_once()

    @pytest.mark.asyncio
    async def test_circuit_open_during_call_returns_skipped(self) -> None:
        profile = _make_profile()
        db = _mock_db_with_profile(profile)

        with patch(
            "services.ingestor.jobs._get_source_probe_breaker",
        ) as mock_breaker_fn:
            breaker = MagicMock(spec=CircuitBreaker)
            breaker.is_open = False
            breaker.call = AsyncMock(side_effect=CircuitOpenError())
            mock_breaker_fn.return_value = breaker

            result = await run_source_probe(db, source_id=1)

        assert result["skipped"] is True
        assert result["reason"] == "circuit_open"

    @pytest.mark.asyncio
    async def test_url_construction(self) -> None:
        profile = _make_profile(
            base_url="https://api.example.com/",
            health_check_path="/v1/health",
        )
        db = _mock_db_with_profile(profile)
        response = _mock_response()

        with (
            patch(
                "services.ingestor.jobs._get_source_probe_breaker",
            ) as mock_breaker_fn,
            patch(
                "services.ingestor.jobs.record_health_sample",
                new_callable=AsyncMock,
            ),
        ):
            breaker = MagicMock(spec=CircuitBreaker)
            breaker.is_open = False
            breaker.call = AsyncMock(return_value=response)
            mock_breaker_fn.return_value = breaker

            result = await run_source_probe(db, source_id=1)

        assert result["target_url"] == "https://api.example.com/v1/health"


# ============================================================================
# run_source_contract_snapshot
# ============================================================================


class TestRunSourceContractSnapshot:
    @pytest.mark.asyncio
    async def test_skips_inactive_source(self) -> None:
        db = _mock_db_with_profile(None)

        result = await run_source_contract_snapshot(db, source_id=999)

        assert result["skipped"] is True
        assert result["reason"] == "source_inactive"

    @pytest.mark.asyncio
    async def test_skips_when_circuit_open(self) -> None:
        profile = _make_profile()
        db = _mock_db_with_profile(profile)

        breaker = MagicMock(spec=CircuitBreaker)
        breaker.is_open = True

        with patch(
            "services.ingestor.jobs._get_source_probe_breaker", return_value=breaker
        ):
            result = await run_source_contract_snapshot(db, source_id=1)

        assert result["skipped"] is True
        assert result["reason"] == "circuit_open"

    @pytest.mark.asyncio
    async def test_successful_snapshot_no_drift(self) -> None:
        profile = _make_profile()
        db = _mock_db_with_profile(profile)
        response = _mock_response(json_data={"users": [{"id": 1, "name": "Alice"}]})

        snapshot = MagicMock(spec=ContractSnapshot)
        snapshot.id = 42

        with (
            patch(
                "services.ingestor.jobs._get_source_probe_breaker",
            ) as mock_breaker_fn,
            patch(
                "services.ingestor.jobs.get_http_client",
            ) as mock_get_client,
            patch(
                "services.ingestor.jobs.create_contract_snapshot",
                new_callable=AsyncMock,
                return_value=(snapshot, None),
            ),
        ):
            breaker = MagicMock(spec=CircuitBreaker)
            breaker.is_open = False
            breaker.call = AsyncMock(return_value=response)
            mock_breaker_fn.return_value = breaker

            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await run_source_contract_snapshot(db, source_id=1)

        assert result["source_id"] == 1
        assert result["snapshot_id"] == 42
        assert result["drift_detected"] is False
        assert result["drift_event_id"] is None

    @pytest.mark.asyncio
    async def test_successful_snapshot_with_drift(self) -> None:
        profile = _make_profile()
        db = _mock_db_with_profile(profile)
        response = _mock_response(json_data={"users": [{"id": 1}]})

        snapshot = MagicMock(spec=ContractSnapshot)
        snapshot.id = 43
        drift_event = MagicMock(spec=DriftEvent)
        drift_event.id = 7

        with (
            patch(
                "services.ingestor.jobs._get_source_probe_breaker",
            ) as mock_breaker_fn,
            patch(
                "services.ingestor.jobs.get_http_client",
            ) as mock_get_client,
            patch(
                "services.ingestor.jobs.create_contract_snapshot",
                new_callable=AsyncMock,
                return_value=(snapshot, drift_event),
            ),
        ):
            breaker = MagicMock(spec=CircuitBreaker)
            breaker.is_open = False
            breaker.call = AsyncMock(return_value=response)
            mock_breaker_fn.return_value = breaker

            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await run_source_contract_snapshot(db, source_id=1)

        assert result["drift_detected"] is True
        assert result["drift_event_id"] == 7
        assert result["snapshot_id"] == 43

    @pytest.mark.asyncio
    async def test_http_error_returns_fetch_failed(self) -> None:
        profile = _make_profile()
        db = _mock_db_with_profile(profile)

        with (
            patch(
                "services.ingestor.jobs._get_source_probe_breaker",
            ) as mock_breaker_fn,
            patch(
                "services.ingestor.jobs.get_http_client",
            ) as mock_get_client,
        ):
            breaker = MagicMock(spec=CircuitBreaker)
            breaker.is_open = False
            breaker.call = AsyncMock(
                side_effect=httpx.ConnectError("connection refused")
            )
            mock_breaker_fn.return_value = breaker

            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await run_source_contract_snapshot(db, source_id=1)

        assert result["skipped"] is True
        assert result["reason"] == "fetch_failed"

    @pytest.mark.asyncio
    async def test_non_dict_response_returns_skipped(self) -> None:
        profile = _make_profile()
        db = _mock_db_with_profile(profile)
        response = _mock_response(json_data=[1, 2, 3])  # type: ignore[arg-type]

        with (
            patch(
                "services.ingestor.jobs._get_source_probe_breaker",
            ) as mock_breaker_fn,
            patch(
                "services.ingestor.jobs.get_http_client",
            ) as mock_get_client,
        ):
            breaker = MagicMock(spec=CircuitBreaker)
            breaker.is_open = False
            breaker.call = AsyncMock(return_value=response)
            mock_breaker_fn.return_value = breaker

            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await run_source_contract_snapshot(db, source_id=1)

        assert result["skipped"] is True
        assert result["reason"] == "non_dict_response"

    @pytest.mark.asyncio
    async def test_json_decode_error_returns_fetch_failed(self) -> None:
        profile = _make_profile()
        db = _mock_db_with_profile(profile)

        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.raise_for_status = MagicMock()
        response.json.side_effect = ValueError("invalid JSON")

        with (
            patch(
                "services.ingestor.jobs._get_source_probe_breaker",
            ) as mock_breaker_fn,
            patch(
                "services.ingestor.jobs.get_http_client",
            ) as mock_get_client,
        ):
            breaker = MagicMock(spec=CircuitBreaker)
            breaker.is_open = False
            breaker.call = AsyncMock(return_value=response)
            mock_breaker_fn.return_value = breaker

            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await run_source_contract_snapshot(db, source_id=1)

        assert result["skipped"] is True
        assert result["reason"] == "fetch_failed"

    @pytest.mark.asyncio
    async def test_circuit_open_during_call_returns_fetch_failed(self) -> None:
        profile = _make_profile()
        db = _mock_db_with_profile(profile)

        with (
            patch(
                "services.ingestor.jobs._get_source_probe_breaker",
            ) as mock_breaker_fn,
            patch(
                "services.ingestor.jobs.get_http_client",
            ) as mock_get_client,
        ):
            breaker = MagicMock(spec=CircuitBreaker)
            breaker.is_open = False
            breaker.call = AsyncMock(side_effect=CircuitOpenError())
            mock_breaker_fn.return_value = breaker

            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await run_source_contract_snapshot(db, source_id=1)

        assert result["skipped"] is True
        assert result["reason"] == "fetch_failed"
