"""Panel: Live Stream (WebSocket) for real-time events.

Split into:
  - ``use_ws_connection`` — connection lifecycle (start/stop/drain)
  - ``render_live_stream`` — pure UI display
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from datetime import UTC, datetime

from services.dashboard.core.auth import AuthManager
from services.dashboard.core.config import config
from services.dashboard.ui.protocols import UIAdapter


# ---------------------------------------------------------------------------
# Hook
# ---------------------------------------------------------------------------


def use_ws_connection(ui: UIAdapter, auth: AuthManager) -> dict:
    """Ensure the WS thread is running or stopped based on flag; drain buffer.

    Returns a dict with ``connected`` and ``messages`` keys.
    """
    if ui.ws_connected:
        import websockets as _ws

        _stop = ui.ws_stop_event
        _buf = ui.ws_buffer
        _ws_token = auth.access_token
        _ws_url = (
            config.ingestor_url.replace("http://", "ws://").replace(
                "https://", "wss://"
            )
            + "/ws/observations/stream"
        )
        if _ws_token:
            _ws_url = f"{_ws_url}?token={_ws_token}"

        def _ws_thread() -> None:
            async def _listen() -> None:
                try:
                    async with _ws.connect(
                        _ws_url, open_timeout=3, ping_timeout=None
                    ) as sock:
                        async for raw in sock:
                            if _stop.is_set():
                                break
                            try:
                                msg = json.loads(raw)
                            except json.JSONDecodeError:
                                msg = {"type": "raw", "data": raw}
                            _buf.put_nowait(msg)
                except Exception as exc:
                    _buf.put_nowait(
                        {
                            "type": "info",
                            "message": f"Connection error: {exc}",
                            "ts": datetime.now(tz=UTC).isoformat(),
                        }
                    )
                    _stop.set()

            asyncio.run(_listen())

        if ui.ws_thread is None or not ui.ws_thread.is_alive():
            _stop.clear()
            t = threading.Thread(target=_ws_thread, daemon=True)
            t.start()
            ui.set_ws_thread(t)

        while not _buf.empty():
            try:
                ui.ws_messages.append(_buf.get_nowait())
            except queue.Empty:
                break

        if len(ui.ws_messages) > config.max_stream_messages * 2:
            ui.ws_messages = ui.ws_messages[-config.max_stream_messages :]

        if _stop.is_set():
            ui.ws_connected = False

    return {
        "connected": ui.ws_connected,
        "messages": ui.ws_messages[-config.max_stream_messages :],
    }


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------


def _render_messages(ui: UIAdapter, data: dict) -> None:
    msgs = data["messages"]
    if not msgs:
        ui.empty().info("No messages yet — connect to start streaming.")
        return

    lines = []
    for m in reversed(msgs):
        ts = m.get("ts", "")[:19].replace("T", " ")
        mtype = m.get("type", "unknown")
        icon = {
            "observation.created": "📥",
            "drift.detected": "⚠️",
            "job.progress": "⏳",
            "ping": "💓",
            "info": "ℹ️",
        }.get(mtype, "📨")
        lines.append(
            f"`{ts}` {icon} **{mtype}** — "
            + json.dumps({k: v for k, v in m.items() if k not in ("type", "ts")})
        )

    ui.empty().markdown("\n\n".join(lines))


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------


def render_live_stream(ui: UIAdapter, auth: AuthManager) -> None:
    """Render the WebSocket live stream panel."""
    ui.header("Live Stream")
    ui.caption(
        "Receives `observation.created`, `drift.detected`, `job.progress`, and `ping` events."
    )

    col_connect, col_clear = ui.columns([1, 1])
    connect_btn = col_connect.button(
        "🔌 Disconnect" if ui.ws_connected else "🔌 Connect",
        key="ws_toggle",
    )
    col_clear.button(
        "🗑 Clear", key="ws_clear", on_click=lambda: setattr(ui, "ws_messages", [])
    )

    if connect_btn:
        ui.ws_connected = not ui.ws_connected
        if not ui.ws_connected:
            ui.ws_stop_event.set()

    data = use_ws_connection(ui, auth)

    if data["connected"]:
        time.sleep(1)
        ui.rerun()

    _render_messages(ui, data)
