"""Deterministic unit coverage for external fetch resilience behavior."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import httpx
import pytest

import services.ingestor.fetch as fetch_module


pytestmark = pytest.mark.unit


class _Response:
    def __init__(self, body: object, error: Exception | None = None) -> None:
        self._body = body
        self._error = error

    def raise_for_status(self) -> None:
        if self._error is not None:
            raise self._error

    def json(self) -> object:
        return self._body


class _Client:
    def __init__(self, response: _Response) -> None:
        self.get = AsyncMock(return_value=response)


@pytest.fixture(autouse=True)
async def _cleanup_http_clients() -> AsyncIterator[None]:
    yield
    await fetch_module.close_all_http_clients()


async def test_simulated_failure_uses_the_secrets_seam_before_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_client = AsyncMock()
    monkeypatch.setattr(fetch_module, "get_http_client", get_client)

    with (
        patch("secrets.randbelow", return_value=0),
        pytest.raises(Exception, match="Simulated API failure"),
    ):
        await fetch_module.fetch_from_external_api(
            "https://example.invalid/resource",
            simulate_failures=True,
        )

    get_client.assert_not_awaited()


async def test_fetch_returns_json_and_uses_the_shared_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _Client(_Response({"id": 1, "title": "deterministic"}))
    monkeypatch.setattr(fetch_module, "get_http_client", AsyncMock(return_value=client))

    result = await fetch_module.fetch_from_external_api("https://example.test/resource")

    assert result == {"id": 1, "title": "deterministic"}
    client.get.assert_awaited_once_with("https://example.test/resource")


async def test_fetch_logs_timeout_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _Client(_Response({}, httpx.TimeoutException("timeout")))
    monkeypatch.setattr(fetch_module, "get_http_client", AsyncMock(return_value=client))

    with pytest.raises(httpx.TimeoutException, match="timeout"):
        await fetch_module.fetch_from_external_api("https://example.test/resource")


async def test_fetch_logs_http_status_error_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = httpx.Request("GET", "https://example.test/resource")
    response = httpx.Response(503, request=request)
    error = httpx.HTTPStatusError("unavailable", request=request, response=response)
    client = _Client(_Response({}, error))
    monkeypatch.setattr(fetch_module, "get_http_client", AsyncMock(return_value=client))

    with pytest.raises(httpx.HTTPStatusError, match="unavailable"):
        await fetch_module.fetch_from_external_api("https://example.test/resource")


async def test_retry_succeeds_after_transient_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    async def flaky_fetch(_url: str, simulate_failures: bool = False) -> dict[str, int]:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ConnectError("temporary")
        return {"id": 1}

    sleep = AsyncMock()
    monkeypatch.setattr(fetch_module, "fetch_from_external_api", flaky_fetch)
    monkeypatch.setattr(fetch_module.asyncio, "sleep", sleep)

    result = await fetch_module.fetch_with_retry(
        "https://example.test/resource", max_retries=3
    )

    assert result == {"id": 1}
    assert attempts == 3
    assert [call.args[0] for call in sleep.await_args_list] == [1, 2]


async def test_retry_reraises_the_final_failure_without_sleeping_after_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failing_fetch = AsyncMock(side_effect=httpx.ConnectError("unavailable"))
    sleep = AsyncMock()
    monkeypatch.setattr(fetch_module, "fetch_from_external_api", failing_fetch)
    monkeypatch.setattr(fetch_module.asyncio, "sleep", sleep)

    with pytest.raises(httpx.ConnectError, match="unavailable"):
        await fetch_module.fetch_with_retry(
            "https://example.test/resource", max_retries=3
        )

    assert failing_fetch.await_count == 3
    assert [call.args[0] for call in sleep.await_args_list] == [1, 2]


async def test_http_client_is_reused_then_closed() -> None:
    first = await fetch_module.get_http_client()
    second = await fetch_module.get_http_client()

    assert first is second
    await fetch_module.close_http_client()
    assert first.is_closed is True
