"""API Observatory — Streamlit dashboard.

Three panels:
  1. Source Health  — scorecards table (auto-refreshed every 30 s)
  2. Drift Events   — recent drift events across all sources (auto-refreshed)
  3. Live Stream    — WebSocket event tail (connect/disconnect manually)

Configuration (environment variables or .streamlit/secrets.toml):
  INGESTOR_URL   Base URL of the ingestor service (default: http://localhost:8000)
  BEARER_TOKEN   Optional bearer token for the WebSocket endpoint
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
import time
from datetime import UTC, datetime

import httpx
import streamlit as st


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

INGESTOR_URL: str = os.environ.get("INGESTOR_URL", "http://localhost:8000").rstrip("/")

try:
    _token_from_secrets: str = st.secrets.get("BEARER_TOKEN", "") or ""  # type: ignore[union-attr]
except Exception:
    _token_from_secrets = ""  # nosec B105 — empty default, not a hardcoded password
BEARER_TOKEN: str = _token_from_secrets or os.environ.get("BEARER_TOKEN", "")
WS_URL: str = (
    INGESTOR_URL.replace("http://", "ws://").replace("https://", "wss://")
    + "/ws/records/stream"
)
if BEARER_TOKEN:
    WS_URL = f"{WS_URL}?token={BEARER_TOKEN}"

API_SCORECARDS = f"{INGESTOR_URL}/api/v1/scorecards"
API_SOURCES = f"{INGESTOR_URL}/api/v1/sources"
API_DRIFT = f"{INGESTOR_URL}/api/v1/contracts/sources/{{source_id}}/drift-events"

REFRESH_INTERVAL = 30  # seconds between auto-refreshes for health / drift panels
MAX_STREAM_MESSAGES = 50

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="API Observatory",
    page_icon="🔭",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.title("🔭 API Observatory")
st.caption(f"Ingestor: `{INGESTOR_URL}`")

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


@st.cache_data(ttl=REFRESH_INTERVAL, show_spinner=False)
def fetch_scorecards() -> list[dict]:
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(API_SCORECARDS, params={"limit": 50})
            r.raise_for_status()
            return r.json().get("items", [])
    except Exception as exc:  # noqa: BLE001
        return [{"_error": str(exc)}]


@st.cache_data(ttl=REFRESH_INTERVAL, show_spinner=False)
def fetch_sources() -> list[dict]:
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(API_SOURCES, params={"limit": 50})
            r.raise_for_status()
            return r.json().get("items", [])
    except Exception:  # noqa: BLE001
        return []


@st.cache_data(ttl=REFRESH_INTERVAL, show_spinner=False)
def fetch_drift_events(source_id: int) -> list[dict]:
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(API_DRIFT.format(source_id=source_id), params={"limit": 20})
            r.raise_for_status()
            return r.json().get("items", [])
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------

if "ws_messages" not in st.session_state:
    st.session_state.ws_messages: list[dict] = []
if "ws_connected" not in st.session_state:
    st.session_state.ws_connected: bool = False
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh: float = 0.0
# Thread-safe primitives — background threads must NOT access st.session_state directly.
if "_ws_stop" not in st.session_state:
    st.session_state["_ws_stop"] = threading.Event()
if "_ws_buf" not in st.session_state:
    st.session_state["_ws_buf"] = queue.Queue()

# ---------------------------------------------------------------------------
# Panel 1: Source Health
# ---------------------------------------------------------------------------

st.header("Source Health")

scorecards = fetch_scorecards()

if scorecards and "_error" in scorecards[0]:
    st.error(f"Could not reach ingestor: {scorecards[0]['_error']}")
elif not scorecards:
    st.info("No scorecards yet — seed some sources and wait for the first probe cycle.")
else:
    rows = []
    for sc in scorecards:
        uptime = sc.get("uptime_pct")
        p95 = sc.get("p95_latency_ms")
        burn = sc.get("error_budget_burn_rate")
        rows.append(
            {
                "Source ID": sc.get("source_id", "—"),
                "Uptime %": f"{uptime:.1f}" if uptime is not None else "—",
                "p95 Latency ms": f"{p95:.0f}" if p95 is not None else "—",
                "Error Budget Burn": f"{burn:.2f}x" if burn is not None else "—",
                "Status": "🟢"
                if (uptime or 0) >= 99
                else "🟡"
                if (uptime or 0) >= 95
                else "🔴",
            }
        )
    st.dataframe(rows, use_container_width=True)

# ---------------------------------------------------------------------------
# Panel 2: Drift Events
# ---------------------------------------------------------------------------

st.header("Drift Events")

sources = fetch_sources()
if not sources:
    st.info("No sources registered yet.")
else:
    all_drift: list[dict] = []
    for src in sources:
        events = fetch_drift_events(src["id"])
        for ev in events:
            all_drift.append(
                {
                    "Source": src.get("name", src["id"]),
                    "Detected": ev.get("detected_at", "—")[:19].replace("T", " "),
                    "Type": ev.get("event_type", "—"),
                    "Severity": ev.get("severity", "—"),
                    "Score": f"{ev.get('compatibility_score', 0):.1f}",
                    "Summary": ev.get("summary", "—"),
                }
            )

    # Sort newest first
    all_drift.sort(key=lambda r: r["Detected"], reverse=True)

    if not all_drift:
        st.info("No drift events detected yet.")
    else:
        severity_icon = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🔵",
            "none": "⚪",
        }
        for row in all_drift:
            row["Severity"] = (
                f"{severity_icon.get(row['Severity'], '')} {row['Severity']}"
            )
        st.dataframe(all_drift[:50], use_container_width=True)

# ---------------------------------------------------------------------------
# Panel 3: Live Stream (WebSocket)
# ---------------------------------------------------------------------------

st.header("Live Stream")
st.caption(
    "Receives `record.created`, `drift.detected`, `job.progress`, and `ping` events."
)

col_connect, col_clear = st.columns([1, 1])
connect_btn = col_connect.button(
    "🔌 Disconnect" if st.session_state.ws_connected else "🔌 Connect",
    key="ws_toggle",
)
col_clear.button(
    "🗑 Clear", key="ws_clear", on_click=lambda: st.session_state.ws_messages.clear()
)

if connect_btn:
    new_connected = not st.session_state.ws_connected
    st.session_state.ws_connected = new_connected
    if not new_connected:
        st.session_state["_ws_stop"].set()  # signal background thread to exit

msg_container = st.empty()


def _render_messages() -> None:
    msgs = st.session_state.ws_messages[-MAX_STREAM_MESSAGES:]
    if not msgs:
        msg_container.info("No messages yet — connect to start streaming.")
        return
    lines = []
    for m in reversed(msgs):
        ts = m.get("ts", "")[:19].replace("T", " ")
        mtype = m.get("type", "unknown")
        icon = {
            "record.created": "📥",
            "drift.detected": "⚠️",
            "job.progress": "⏳",
            "ping": "💓",
            "info": "ℹ️",
        }.get(mtype, "📨")
        lines.append(
            f"`{ts}` {icon} **{mtype}** — "
            + json.dumps({k: v for k, v in m.items() if k not in ("type", "ts")})
        )
    msg_container.markdown("\n\n".join(lines))


if st.session_state.ws_connected:
    import websockets as _ws  # type: ignore[import-untyped]

    # Capture thread-safe primitives by value — the closure must never touch
    # st.session_state because background threads have no ScriptRunContext.
    _stop: threading.Event = st.session_state["_ws_stop"]
    _buf: queue.Queue = st.session_state["_ws_buf"]

    def _ws_thread() -> None:
        async def _listen() -> None:
            try:
                async with _ws.connect(
                    WS_URL, open_timeout=3, ping_timeout=None
                ) as sock:
                    async for raw in sock:
                        if _stop.is_set():
                            break
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            msg = {"type": "raw", "data": raw}
                        _buf.put_nowait(msg)
            except Exception as exc:  # noqa: BLE001
                _buf.put_nowait(
                    {
                        "type": "info",
                        "message": f"Connection error: {exc}",
                        "ts": datetime.now(tz=UTC).isoformat(),
                    }
                )
                _stop.set()  # signals main loop to flip ws_connected = False

        asyncio.run(_listen())

    if (
        "_ws_thread" not in st.session_state
        or not st.session_state["_ws_thread"].is_alive()
    ):
        st.session_state["_ws_stop"].clear()  # reset for fresh connection
        t = threading.Thread(target=_ws_thread, daemon=True)
        t.start()
        st.session_state["_ws_thread"] = t

    # Drain messages from thread-safe queue into session state (main thread only).
    while not st.session_state["_ws_buf"].empty():
        try:
            st.session_state.ws_messages.append(
                st.session_state["_ws_buf"].get_nowait()
            )
        except queue.Empty:
            break
    if len(st.session_state.ws_messages) > MAX_STREAM_MESSAGES * 2:
        st.session_state.ws_messages = st.session_state.ws_messages[
            -MAX_STREAM_MESSAGES:
        ]

    # If the thread signaled an error, flip the toggle in main thread.
    if st.session_state["_ws_stop"].is_set():
        st.session_state.ws_connected = False

    # Auto-rerun every second while connected so messages appear live.
    time.sleep(1)
    st.rerun()

_render_messages()

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()
last = (
    datetime.fromtimestamp(st.session_state.last_refresh, tz=UTC).strftime("%H:%M:%S")
    if st.session_state.last_refresh
    else "never"
)
col_r, col_auto = st.columns([3, 1])
col_r.caption(
    f"Data last fetched from `{INGESTOR_URL}` — cache TTL {REFRESH_INTERVAL}s"
)
if col_auto.button("🔄 Refresh now"):
    st.cache_data.clear()
    st.session_state.last_refresh = time.time()
    st.rerun()
