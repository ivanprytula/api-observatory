"""Integration tests for WebSocket endpoint (/ws/observations/stream).

Tests cover auth, cache-disabled fallback, and connection lifecycle.
Since httpx.AsyncClient does not support WebSocket handshakes, these tests
call the ``observations_stream`` handler directly with mock WebSocket objects.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import jwt
import pytest

from services.ingestor.auth import create_jwt_token
from services.ingestor.config import settings
from services.ingestor.routers.ws import _manager, observations_stream


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
