from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, patch

import jwt
import pytest

from services.ingestor.auth import create_jwt_token
from services.ingestor.config import settings
from services.ingestor.routers.ws import _manager, _stream_events, observations_stream


@pytest.fixture(autouse=True)
def _reset_manager():
    """Clear active connections before/after each test."""
    _manager._active.clear()
    yield
    _manager._active.clear()


# ---------------------------------------------------------------------------
# Auth — missing token (jwt_secret configured)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.ws_lab
async def test_ws_missing_token_rejected() -> None:
    """Client without ?token= is closed with code 4001 when auth is enabled."""
    ws_mock = AsyncMock(spec_set=["close", "accept", "send_json"])
    ws_mock.close = AsyncMock()

    with patch.object(settings, "jwt_secret", "test-secret"):
        await observations_stream(websocket=ws_mock, token=None)

    ws_mock.close.assert_awaited_once_with(code=4001, reason="missing token")
    ws_mock.accept.assert_not_called()


# ---------------------------------------------------------------------------
# Auth — invalid token (jwt_secret configured)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.ws_lab
async def test_ws_invalid_token_rejected() -> None:
    """Client with a bad token is closed with code 4003."""
    ws_mock = AsyncMock(spec_set=["close", "accept", "send_json"])
    ws_mock.close = AsyncMock()

    with patch.object(settings, "jwt_secret", "test-secret"):
        await observations_stream(websocket=ws_mock, token="invalid-token")

    ws_mock.close.assert_awaited_once_with(code=4003, reason="invalid token")
    ws_mock.accept.assert_not_called()


# ---------------------------------------------------------------------------
# Auth — valid token (jwt_secret configured)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.ws_lab
async def test_ws_valid_token_accepted() -> None:
    """Client with a valid JWT is accepted when auth is enabled."""
    ws_mock = AsyncMock(spec_set=["close", "accept", "send_json"])
    ws_mock.close = AsyncMock()
    ws_mock.accept = AsyncMock()
    ws_mock.send_json = AsyncMock()

    with (
        patch.object(settings, "jwt_secret", "test-secret"),
        patch(
            "services.ingestor.routers.ws._idle_until_disconnect",
            AsyncMock(),
        ),
    ):
        token = create_jwt_token("test-user")
        await observations_stream(websocket=ws_mock, token=token)

    ws_mock.accept.assert_awaited_once()
    ws_mock.send_json.assert_awaited_once_with(
        {"type": "info", "message": "stream unavailable: Cache not enabled"},
    )
    ws_mock.close.assert_not_called()


# ---------------------------------------------------------------------------
# Auth — expired token
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.ws_lab
async def test_ws_expired_token_rejected() -> None:
    """Client with an expired token is closed with code 4003."""
    ws_mock = AsyncMock(spec_set=["close", "accept", "send_json"])
    ws_mock.close = AsyncMock()

    with patch.object(settings, "jwt_secret", "test-secret"):
        # Build a token that is already expired
        expiry_payload = {
            "sub": "test-user",
            "exp": 1_000_000,  # way in the past
            "iat": 1_000_000,
            "iss": settings.app_name,
        }
        expired_token = jwt.encode(expiry_payload, "test-secret", algorithm="HS256")
        await observations_stream(websocket=ws_mock, token=expired_token)

    ws_mock.close.assert_awaited_once_with(code=4003, reason="invalid token")


# ---------------------------------------------------------------------------
# Auth — disabled (jwt_secret is empty/not configured)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.ws_lab
async def test_ws_auth_disabled_accepts_any_token() -> None:
    """When jwt_secret is empty, all clients are accepted regardless of token."""
    ws_mock = AsyncMock(spec_set=["close", "accept", "send_json"])
    ws_mock.close = AsyncMock()
    ws_mock.accept = AsyncMock()
    ws_mock.send_json = AsyncMock()

    with (
        patch.object(settings, "jwt_secret", ""),
        patch(
            "services.ingestor.routers.ws._idle_until_disconnect",
            AsyncMock(),
        ),
    ):
        await observations_stream(websocket=ws_mock, token=None)
        ws_mock.close.assert_not_called()

    ws_mock.accept.assert_awaited_once()


@pytest.mark.integration
@pytest.mark.ws_lab
async def test_ws_auth_disabled_ignores_invalid_token() -> None:
    """Even with a garbage token, auth-disabled mode accepts the connection."""
    ws_mock = AsyncMock(spec_set=["close", "accept", "send_json"])
    ws_mock.close = AsyncMock()
    ws_mock.accept = AsyncMock()
    ws_mock.send_json = AsyncMock()

    with (
        patch.object(settings, "jwt_secret", ""),
        patch(
            "services.ingestor.routers.ws._idle_until_disconnect",
            AsyncMock(),
        ),
    ):
        await observations_stream(websocket=ws_mock, token="garbage-token")
        ws_mock.close.assert_not_called()

    ws_mock.accept.assert_awaited_once()


# ---------------------------------------------------------------------------
# Cache-disabled fallback (default in tests: CACHE_ENABLED=false)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.ws_lab
async def test_ws_cache_disabled_sends_info_and_idles() -> None:
    """When cache is disabled, handler sends info message then idles."""
    ws_mock = AsyncMock(spec_set=["close", "accept", "send_json"])
    ws_mock.close = AsyncMock()
    ws_mock.accept = AsyncMock()
    ws_mock.send_json = AsyncMock()

    with (
        patch.object(settings, "jwt_secret", ""),
        patch(
            "services.ingestor.routers.ws._idle_until_disconnect",
            AsyncMock(),
        ) as mock_idle,
    ):
        await observations_stream(websocket=ws_mock, token=None)

    ws_mock.accept.assert_awaited_once()
    ws_mock.send_json.assert_awaited_once_with(
        {"type": "info", "message": "stream unavailable: Cache not enabled"},
    )
    mock_idle.assert_awaited_once_with(ws_mock)


# ---------------------------------------------------------------------------
# Connection lifecycle — manager tracks active connections
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.ws_lab
async def test_ws_manager_tracks_connection_lifecycle() -> None:
    """_manager.connect / disconnect are called on accept / cleanup."""
    ws_mock = AsyncMock(spec_set=["close", "accept", "send_json"])
    ws_mock.close = AsyncMock()
    ws_mock.accept = AsyncMock()
    ws_mock.send_json = AsyncMock()

    assert _manager.count == 0

    with (
        patch.object(settings, "jwt_secret", ""),
        patch(
            "services.ingestor.routers.ws._idle_until_disconnect",
            AsyncMock(),
        ),
    ):
        await observations_stream(websocket=ws_mock, token=None)

    assert _manager.count == 0  # cleaned up in finally


# ---------------------------------------------------------------------------
# Connection lifecycle — WebSocketDisconnect is handled gracefully
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.ws_lab
async def test_ws_disconnect_during_idle_handled_gracefully() -> None:
    """WebSocketDisconnect during _idle_until_disconnect does not propagate."""
    ws_mock = AsyncMock(spec_set=["close", "accept", "send_json"])
    ws_mock.close = AsyncMock()
    ws_mock.accept = AsyncMock()
    ws_mock.send_json = AsyncMock()

    async def _simulate_disconnect(*_args: object) -> None:
        from fastapi import WebSocketDisconnect

        raise WebSocketDisconnect()

    with (
        patch.object(settings, "jwt_secret", ""),
        patch(
            "services.ingestor.routers.ws._idle_until_disconnect",
            _simulate_disconnect,
        ),
    ):
        # Should not raise — the handler catches WebSocketDisconnect
        await observations_stream(websocket=ws_mock, token=None)

    ws_mock.accept.assert_awaited_once()
    ws_mock.send_json.assert_awaited_once()
    assert _manager.count == 0


# ---------------------------------------------------------------------------
# Event forwarding — pub/sub → WebSocket client
# ---------------------------------------------------------------------------


async def _fake_events(
    events: list[dict[str, Any]],
) -> AsyncGenerator[dict[str, Any]]:
    for event in events:
        yield event


@pytest.mark.integration
@pytest.mark.ws_lab
async def test_ws_forwards_drift_event_to_client() -> None:
    """A drift.detected event from pub/sub is forwarded via send_json."""
    drift_event = {
        "type": "drift.detected",
        "source_id": 1,
        "drift_event_id": 7,
        "event_type": "breaking",
        "severity": "high",
        "compatibility_score": 72.5,
        "ts": "2026-06-25T12:00:00+00:00",
    }

    ws_mock = AsyncMock(spec_set=["close", "accept", "send_json"])
    ws_mock.send_json = AsyncMock()

    with patch(
        "services.ingestor.routers.ws.pubsub.subscribe_events",
        return_value=_fake_events([drift_event]),
    ):
        await _stream_events(ws_mock)

    ws_mock.send_json.assert_any_call(drift_event)


@pytest.mark.integration
@pytest.mark.ws_lab
async def test_ws_forwards_multiple_events_in_order() -> None:
    """Multiple events are forwarded in the order they arrive."""
    events = [
        {"type": "observation.created", "observation_id": 1, "source": "api-a"},
        {"type": "drift.detected", "source_id": 1, "drift_event_id": 3},
        {"type": "job.progress", "job_id": "j1", "status": "complete"},
    ]

    ws_mock = AsyncMock(spec_set=["close", "accept", "send_json"])
    ws_mock.send_json = AsyncMock()

    with patch(
        "services.ingestor.routers.ws.pubsub.subscribe_events",
        return_value=_fake_events(events),
    ):
        await _stream_events(ws_mock)

    calls = [c.args[0] for c in ws_mock.send_json.call_args_list]
    assert events[0] in calls
    assert events[1] in calls
    assert events[2] in calls


@pytest.mark.integration
@pytest.mark.ws_lab
async def test_ws_stream_handles_client_disconnect() -> None:
    """Client disconnecting mid-stream stops the reader gracefully."""
    from fastapi import WebSocketDisconnect

    call_count = 0

    async def _events_then_hang() -> AsyncGenerator[dict[str, Any]]:
        nonlocal call_count
        yield {"type": "observation.created", "observation_id": 1, "source": "x"}
        call_count += 1
        await asyncio.sleep(999)

    ws_mock = AsyncMock(spec_set=["close", "accept", "send_json"])

    send_count = 0

    async def _send_then_disconnect(data: Any) -> None:
        nonlocal send_count
        send_count += 1
        if send_count >= 2:
            raise WebSocketDisconnect()

    ws_mock.send_json = _send_then_disconnect

    with patch(
        "services.ingestor.routers.ws.pubsub.subscribe_events",
        return_value=_events_then_hang(),
    ):
        await _stream_events(ws_mock)

    assert call_count == 1


@pytest.mark.integration
@pytest.mark.ws_lab
async def test_ws_full_flow_with_cache_enabled() -> None:
    """End-to-end: auth disabled + cache enabled → events forwarded to client."""
    event = {
        "type": "drift.detected",
        "source_id": 2,
        "drift_event_id": 10,
        "severity": "critical",
    }

    ws_mock = AsyncMock(spec_set=["close", "accept", "send_json"])
    ws_mock.close = AsyncMock()
    ws_mock.accept = AsyncMock()
    ws_mock.send_json = AsyncMock()

    with (
        patch.object(settings, "jwt_secret", ""),
        patch.object(settings, "cache_enabled", True),
        patch(
            "services.ingestor.routers.ws.pubsub.subscribe_events",
            return_value=_fake_events([event]),
        ),
    ):
        await observations_stream(websocket=ws_mock, token=None)

    ws_mock.accept.assert_awaited_once()
    ws_mock.send_json.assert_any_call(event)
    ws_mock.close.assert_not_called()
