"""Unit tests for services/mcp/auth_client.py's token lifecycle."""

from __future__ import annotations

import asyncio
import time

import httpx
import respx

from services.mcp import auth_client


def _mock_token_route(router: respx.MockRouter, **overrides: object) -> respx.Route:
    body = {
        "access_token": "token-1",
        "refresh_token": "refresh-1",
        "token_type": "bearer",
    }
    body.update(overrides)
    return router.post("/api/v1/auth/token").mock(
        return_value=httpx.Response(200, json=body)
    )


async def test_login_populates_token_state(mocked_ingestor: respx.MockRouter) -> None:
    route = _mock_token_route(mocked_ingestor)

    token = await auth_client.get_valid_token()

    assert token == "token-1"
    assert route.call_count == 1


async def test_get_valid_token_reuses_cached_token_when_not_expired(
    mocked_ingestor: respx.MockRouter,
) -> None:
    route = _mock_token_route(mocked_ingestor)

    first = await auth_client.get_valid_token()
    second = await auth_client.get_valid_token()

    assert first == second == "token-1"
    assert route.call_count == 1


async def test_get_valid_token_relogs_in_once_expired(
    mocked_ingestor: respx.MockRouter, monkeypatch
) -> None:
    route = _mock_token_route(mocked_ingestor)
    await auth_client.get_valid_token()
    assert route.call_count == 1

    # Force the cached token to look expired.
    loop = asyncio.get_running_loop()
    state = auth_client._token_states[loop]
    monkeypatch.setattr(time, "monotonic", lambda: state.expires_at + 1, raising=True)

    token = await auth_client.get_valid_token()

    assert token == "token-1"
    assert route.call_count == 2


async def test_concurrent_expired_calls_trigger_exactly_one_login(
    mocked_ingestor: respx.MockRouter, monkeypatch
) -> None:
    route = _mock_token_route(mocked_ingestor)
    await auth_client.get_valid_token()
    assert route.call_count == 1

    loop = asyncio.get_running_loop()
    state = auth_client._token_states[loop]
    monkeypatch.setattr(time, "monotonic", lambda: state.expires_at + 1, raising=True)

    results = await asyncio.gather(*(auth_client.get_valid_token() for _ in range(5)))

    assert all(token == "token-1" for token in results), results
    assert route.call_count == 2  # one initial login (above) + one re-login


async def test_force_relogin_discards_cache_and_fetches_a_fresh_token(
    mocked_ingestor: respx.MockRouter,
) -> None:
    route = _mock_token_route(mocked_ingestor)
    await auth_client.get_valid_token()
    assert route.call_count == 1

    token = await auth_client.force_relogin()

    assert token == "token-1"
    assert route.call_count == 2
