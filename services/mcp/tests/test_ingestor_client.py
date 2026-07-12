"""Unit tests for services/mcp/ingestor_client.py — path/method/params and the
401-triggers-one-forced-relogin-and-retry behavior."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from services.mcp import ingestor_client


def _mock_login(router: respx.MockRouter, token: str = "token-1") -> respx.Route:
    return router.post("/api/v1/auth/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": token,
                "refresh_token": "refresh",
                "token_type": "bearer",
            },
        )
    )


async def test_list_sources_sends_expected_path_and_params(
    mocked_ingestor: respx.MockRouter,
) -> None:
    _mock_login(mocked_ingestor)
    route = mocked_ingestor.get("/api/v1/sources").mock(
        return_value=httpx.Response(200, json={"items": [], "total": 0})
    )

    result = await ingestor_client.list_sources(is_active=True, offset=5, limit=10)

    assert result == {"items": [], "total": 0}
    sent = route.calls.last.request
    assert sent.url.params["is_active"] == "true"
    assert sent.url.params["offset"] == "5"
    assert sent.url.params["limit"] == "10"
    assert sent.headers["Authorization"] == "Bearer token-1"


async def test_get_source_sends_expected_path(
    mocked_ingestor: respx.MockRouter,
) -> None:
    _mock_login(mocked_ingestor)
    mocked_ingestor.get("/api/v1/sources/42").mock(
        return_value=httpx.Response(200, json={"id": 42, "name": "demo"})
    )

    result = await ingestor_client.get_source(42)

    assert result == {"id": 42, "name": "demo"}


async def test_get_source_404_raises_http_status_error(
    mocked_ingestor: respx.MockRouter,
) -> None:
    _mock_login(mocked_ingestor)
    mocked_ingestor.get("/api/v1/sources/999").mock(
        return_value=httpx.Response(404, json={"detail": "Source not found."})
    )

    with pytest.raises(httpx.HTTPStatusError):
        await ingestor_client.get_source(999)


async def test_list_scorecards_omits_unset_params(
    mocked_ingestor: respx.MockRouter,
) -> None:
    _mock_login(mocked_ingestor)
    route = mocked_ingestor.get("/api/v1/scorecards").mock(
        return_value=httpx.Response(200, json={"items": [], "total": 0})
    )

    await ingestor_client.list_scorecards()

    sent = route.calls.last.request
    assert dict(sent.url.params) == {}


async def test_resume_agent_run_posts_approve_body(
    mocked_ingestor: respx.MockRouter,
) -> None:
    _mock_login(mocked_ingestor)
    route = mocked_ingestor.post("/api/v1/agent/runs/7/resume").mock(
        return_value=httpx.Response(200, json={"id": 7, "status": "approved"})
    )

    result = await ingestor_client.resume_agent_run(7, approve=True)

    assert result == {"id": 7, "status": "approved"}
    assert json.loads(route.calls.last.request.content) == {"approve": True}


async def test_401_triggers_one_forced_relogin_and_retry(
    mocked_ingestor: respx.MockRouter,
) -> None:
    login_route = mocked_ingestor.post("/api/v1/auth/token").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "access_token": "stale-token",
                    "refresh_token": "r1",
                    "token_type": "bearer",
                },
            ),
            httpx.Response(
                200,
                json={
                    "access_token": "fresh-token",
                    "refresh_token": "r2",
                    "token_type": "bearer",
                },
            ),
        ]
    )
    sources_route = mocked_ingestor.get("/api/v1/sources/1").mock(
        side_effect=[
            httpx.Response(401, json={"detail": "Token expired"}),
            httpx.Response(200, json={"id": 1, "name": "demo"}),
        ]
    )

    result = await ingestor_client.get_source(1)

    assert result == {"id": 1, "name": "demo"}
    assert login_route.call_count == 2
    assert sources_route.call_count == 2
    first_call, second_call = sources_route.calls
    assert first_call.request.headers["Authorization"] == "Bearer stale-token"
    assert second_call.request.headers["Authorization"] == "Bearer fresh-token"


async def test_401_on_retry_still_raises(mocked_ingestor: respx.MockRouter) -> None:
    _mock_login(mocked_ingestor)
    mocked_ingestor.get("/api/v1/sources/1").mock(
        return_value=httpx.Response(401, json={"detail": "still unauthorized"})
    )

    with pytest.raises(httpx.HTTPStatusError):
        await ingestor_client.get_source(1)
