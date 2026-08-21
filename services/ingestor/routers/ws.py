"""FastAPI WebSocket endpoint — real-time event stream.

**Lab feature.** Gated behind ``WEBSOCKET_ENABLED=true``; the router is only
mounted in ``main.py`` when explicitly enabled.  The core ingestor is
fully functional without this endpoint.

Endpoint: ``WS /ws/observations/stream``

Streams all ingestor events to connected browser (or any WS client) in
real time.  Events are multiplexed on a single connection and distinguished
by their ``type`` field:

    {"type": "observation.created", "observation_id": 1, "source": "...", "ts": "..."}
    {"type": "job.progress",   "job_id": "...", "status": "running",
     "progress": 0.4, "message": "Batch 2/5 complete"}

Architecture:

    Browser  ─────────────────────────────  WS /ws/observations/stream
                                                    │
                                            subscribe_events()
                                                    │
                                           Cache SUBSCRIBE ingestor:events
                                                    │
                                          Ingestor writes / jobs ──► PUBLISH

Graceful fallback: if Cache pub/sub is not enabled (e.g. in tests), the
handler sends a single ``{"type": "info", "message": "stream unavailable"}``
message and keeps the connection open for ping/pong until the client closes.

Authentication: Bearer token or session token — same guard used by REST routes.
The WS handshake passes the token via ``?token=<value>`` query parameter since
browsers cannot set ``Authorization`` headers on WebSocket connections.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)

from services.ingestor import pubsub
from services.ingestor.core.auth import verify_jwt_token_str
from services.ingestor.core.config import settings


logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

# Keepalive ping interval in seconds — keeps NAT/proxy connections alive
_PING_INTERVAL = 30


# ---------------------------------------------------------------------------
# Token dependency (WS handshake passes token in query string)
# ---------------------------------------------------------------------------


async def _ws_token(
    token: Annotated[str | None, Query(alias="token")] = None,
) -> str | None:
    """Extract bearer token from WS query string.

    WebSocket handshakes cannot carry ``Authorization`` headers in browsers,
    so the convention is ``?token=<bearer>`` in the URL.

    Returns:
        Token string if present, or None (the route decides whether to reject).
    """
    return token


# ---------------------------------------------------------------------------
# Connection manager (fan-out to multiple clients)
# ---------------------------------------------------------------------------


class _ConnectionManager:
    """Track active WebSocket connections for logging/metrics.

    Not used for fan-out here (each client has its own Cache subscriber) but
    provides a registry for observability and future broadcast capabilities.
    """

    def __init__(self) -> None:
        self._active: set[WebSocket] = set()

    def connect(self, ws: WebSocket) -> None:
        self._active.add(ws)
        logger.info("ws_client_connected", extra={"active": len(self._active)})

    def disconnect(self, ws: WebSocket) -> None:
        self._active.discard(ws)
        logger.info("ws_client_disconnected", extra={"active": len(self._active)})

    @property
    def count(self) -> int:
        return len(self._active)


_manager = _ConnectionManager()


# ---------------------------------------------------------------------------
# WebSocket route
# ---------------------------------------------------------------------------


@router.websocket("/ws/observations/stream")
async def observations_stream(
    websocket: WebSocket,
    token: Annotated[str | None, Depends(_ws_token)] = None,
) -> None:
    """Stream real-time ingestor events to the client.

    Accepts the WebSocket handshake, then forwards every event published to
    the ``ingestor:events`` Cache Pub/Sub channel until the client disconnects.

    Query parameters:
        token: Bearer token for authentication.  Pass the same value as you
            would in the ``Authorization: Bearer <token>`` header.  Optional
            if the server is running with auth disabled.

    Message shape (JSON):
        Each message is a JSON object with a ``type`` discriminator field:

        - ``{"type": "observation.created", "observation_id": int, "source": str, "ts": str}``
        - ``{"type": "job.progress",   "job_id": str, "status": str,
             "progress": float, "message": str, "ts": str}``
        - ``{"type": "ping"}`` — keepalive sent every 30 s by the server
        - ``{"type": "info",  "message": str}`` — informational / error messages
    """
    # --- Auth (optional, fail-open if no jwt_secret configured) -----------
    # JWT auth via ?token= query param (browsers can't send Authorization headers)
    if settings.jwt_secret:
        if not token:
            await websocket.close(code=4001, reason="missing token")
            return
        try:
            await verify_jwt_token_str(token)
        except HTTPException:
            logger.warning("ws_invalid_token")
            await websocket.close(code=4003, reason="invalid token")
            return

    await websocket.accept()
    _manager.connect(websocket)

    try:
        if not settings.cache_enabled:
            await websocket.send_json(
                {"type": "info", "message": "stream unavailable: Cache not enabled"}
            )
            # Keep connection open so client can still close cleanly
            await _idle_until_disconnect(websocket)
            return

        await _stream_events(websocket)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("ws_unexpected_error", extra={"error": str(exc)})
    finally:
        _manager.disconnect(websocket)


async def _stream_events(websocket: WebSocket) -> None:
    """Subscribe to Cache pub/sub and forward events; send keepalive pings.

    Runs two concurrent tasks:
    - ``_reader``:   receives events from Cache and forwards to WS client
    - ``_pinger``:   sends a ping every ``_PING_INTERVAL`` seconds

    Either task exiting (client disconnect or Cache error) cancels the other.

    Args:
        websocket: Accepted FastAPI WebSocket connection.
    """

    async def _reader() -> None:
        async for event in pubsub.subscribe_events():
            try:
                await websocket.send_json(event)
            except WebSocketDisconnect:
                return
            except Exception as exc:
                logger.warning("ws_send_error", extra={"error": str(exc)})
                return

    async def _pinger() -> None:
        while True:
            await asyncio.sleep(_PING_INTERVAL)
            try:
                await websocket.send_json({"type": "ping"})
            except Exception:
                return

    reader_task = asyncio.create_task(_reader())
    pinger_task = asyncio.create_task(_pinger())

    try:
        # Wait for either task to finish (client disconnect stops the reader)
        done, pending = await asyncio.wait(
            [reader_task, pinger_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
    except asyncio.CancelledError:
        reader_task.cancel()
        pinger_task.cancel()
        raise


async def _idle_until_disconnect(websocket: WebSocket) -> None:
    """Keep the WebSocket open with periodic pings until the client closes.

    Used when Cache is unavailable — the stream is empty but we keep the
    connection so the client can detect the fallback and retry later.

    Args:
        websocket: Accepted FastAPI WebSocket connection.
    """
    while True:
        try:
            await asyncio.sleep(_PING_INTERVAL)
            await websocket.send_json({"type": "ping"})
        except WebSocketDisconnect:
            return
        except Exception:
            return
