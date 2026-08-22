"""E2E tests for the full incident lifecycle: probe failure → incident opened.

Verifies the complete user/data flow from source probe through health sample
recording to incident reconciliation — using a real database session.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.jobs import run_source_probe
from services.ingestor.models import (
    DependencyIncident,
    ProviderHealthSample,
    SourceProfile,
)


pytestmark = pytest.mark.integration


def _make_profile(
    source_id: int = 1,
    base_url: str = "https://api.example.com",
    health_check_path: str = "/health",
    incident_failure_threshold: int = 1,
) -> SourceProfile:
    return SourceProfile(
        id=source_id,
        name=f"source-{source_id}",
        base_url=base_url,
        health_check_path=health_check_path,
        probe_interval_seconds=60,
        is_active=True,
        incident_failure_threshold=incident_failure_threshold,
    )


def _failing_http_client() -> AsyncMock:
    """Mock HTTP client that always raises a connection error."""
    client = AsyncMock()
    client.head = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    return client


def _error_response_client(status_code: int = 503) -> AsyncMock:
    """Mock HTTP client that returns an error HTTP response."""
    client = AsyncMock()
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    client.head = AsyncMock(return_value=resp)
    return client


@pytest.mark.asyncio
class TestSourceProbeIncidentLifecycle:
    async def test_failed_probe_records_health_sample(self, db: AsyncSession) -> None:
        """A failed probe records a ProviderHealthSample with error info."""
        from services.ingestor.jobs import _source_probe_breakers

        _source_probe_breakers.clear()

        source = _make_profile(source_id=1, incident_failure_threshold=3)
        db.add(source)
        await db.commit()
        await db.refresh(source)

        with patch(
            "services.ingestor.jobs.probes.get_http_client",
            return_value=_failing_http_client(),
        ):
            result = await run_source_probe(db, source.id)

        assert result["is_success"] is False
        assert result["status_code"] is None

        # Verify health sample was persisted with error info
        samples = (
            (
                await db.execute(
                    select(ProviderHealthSample).where(
                        ProviderHealthSample.source_id == source.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(samples) == 1
        assert samples[0].is_success is False
        assert samples[0].error_message is not None

    async def test_threshold_failure_opens_incident(self, db: AsyncSession) -> None:
        """When consecutive failures exceed threshold, an incident is opened."""
        from services.ingestor.jobs import _source_probe_breakers

        _source_probe_breakers.clear()

        source = _make_profile(source_id=2, incident_failure_threshold=1)
        db.add(source)
        await db.commit()
        await db.refresh(source)

        with patch(
            "services.ingestor.jobs.probes.get_http_client",
            return_value=_failing_http_client(),
        ):
            result = await run_source_probe(db, source.id)

        assert result["is_success"] is False

        # Verify incident was opened
        incidents = (
            (
                await db.execute(
                    select(DependencyIncident).where(
                        DependencyIncident.source_id == source.id,
                        DependencyIncident.status == "open",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(incidents) == 1
        assert incidents[0].severity == "critical"
        assert "consecutive probes failed" in incidents[0].summary

    async def test_successful_probe_closes_active_incident(
        self, db: AsyncSession
    ) -> None:
        """A successful probe after failures resolves any open incident."""
        from services.ingestor.jobs import _source_probe_breakers

        _source_probe_breakers.clear()

        source = _make_profile(source_id=3, incident_failure_threshold=1)
        db.add(source)
        await db.commit()
        await db.refresh(source)

        # First: fail to open an incident
        with patch(
            "services.ingestor.jobs.probes.get_http_client",
            return_value=_failing_http_client(),
        ):
            await run_source_probe(db, source.id)

        incidents = (
            (
                await db.execute(
                    select(DependencyIncident).where(
                        DependencyIncident.source_id == source.id,
                        DependencyIncident.status == "open",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(incidents) == 1

        # Second: succeed → incident should be resolved
        with (
            patch(
                "services.ingestor.jobs.probes.validate_source_base_url",
            ),
            patch(
                "services.ingestor.jobs.probes.get_http_client",
                return_value=_error_response_client(200),
            ),
        ):
            result = await run_source_probe(db, source.id)

        assert result["is_success"] is True

        open_incidents = (
            (
                await db.execute(
                    select(DependencyIncident).where(
                        DependencyIncident.source_id == source.id,
                        DependencyIncident.status == "open",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(open_incidents) == 0

        resolved_incidents = (
            (
                await db.execute(
                    select(DependencyIncident).where(
                        DependencyIncident.source_id == source.id,
                        DependencyIncident.status == "resolved",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(resolved_incidents) == 1

    async def test_circuit_breaker_skips_probe(self, db: AsyncSession) -> None:
        """When circuit breaker is open, probe is skipped."""
        from services.ingestor.jobs import _source_probe_breakers

        _source_probe_breakers.clear()

        source = _make_profile(source_id=4)
        db.add(source)
        await db.commit()
        await db.refresh(source)

        # Create and force-open the circuit breaker for this source
        from services.ingestor.jobs import _get_source_probe_breaker

        breaker = _get_source_probe_breaker(source.id)
        await breaker.force_open()

        assert breaker.is_open

        result = await run_source_probe(db, source.id)
        assert result["skipped"] is True
        assert result["reason"] == "circuit_open"

    async def test_inactive_source_skipped(self, db: AsyncSession) -> None:
        """Probe returns skipped for inactive/deleted sources."""
        from services.ingestor.jobs import _source_probe_breakers

        _source_probe_breakers.clear()

        source = _make_profile(source_id=5)
        source.is_active = False
        db.add(source)
        await db.commit()
        await db.refresh(source)

        result = await run_source_probe(db, source.id)
        assert result["skipped"] is True
        assert result["reason"] == "source_inactive"
