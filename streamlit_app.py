"""API Observatory — Streamlit dashboard.

Four panels:
  1. Source Health    — scorecards table (auto-refreshed every 30 s)
  2. Drift Events     — recent drift events across all sources (auto-refreshed)
  3. Live Stream      — WebSocket event tail (connect/disconnect manually)
  4. Service Health   — /health and /readyz probe status + links to /metrics

Configuration (environment variables or .streamlit/secrets.toml):
  INGESTOR_URL   Base URL of the ingestor service (default: http://localhost:8000)
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

API_AUTH_TOKEN = f"{INGESTOR_URL}/api/v1/auth/token"
API_AUTH_REFRESH = f"{INGESTOR_URL}/api/v1/auth/refresh"
API_SCORECARDS = f"{INGESTOR_URL}/api/v1/scorecards"
API_SOURCES = f"{INGESTOR_URL}/api/v1/sources"
API_DRIFT = f"{INGESTOR_URL}/api/v1/contracts/sources/{{source_id}}/drift-events"
API_HEALTH = f"{INGESTOR_URL}/health"
API_READYZ = f"{INGESTOR_URL}/readyz"
API_METRICS = f"{INGESTOR_URL}/metrics"
API_AGENT_ENRICH = f"{INGESTOR_URL}/api/v1/agent/enrich/{{observation_id}}"
API_AGENT_REVIEW = f"{INGESTOR_URL}/api/v1/agent/enrich/{{observation_id}}/review"
API_AGENT_RESUME = f"{INGESTOR_URL}/api/v1/agent/runs/{{run_id}}/resume"
API_AGENT_STREAM = f"{INGESTOR_URL}/api/v1/agent/enrich/{{observation_id}}/stream"


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
def fetch_scorecards(token: str = "") -> list[dict]:
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(
                API_SCORECARDS,
                params={"limit": 50},
                headers={"Authorization": f"Bearer {token}"} if token else {},
            )
            if r.status_code == 401:
                return [{"_401": True}]
            r.raise_for_status()
            return r.json().get("items", [])
    except Exception as exc:  # noqa: BLE001
        return [{"_error": str(exc)}]


@st.cache_data(ttl=REFRESH_INTERVAL, show_spinner=False)
def fetch_sources(token: str = "") -> list[dict]:
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(
                API_SOURCES,
                params={"limit": 50},
                headers={"Authorization": f"Bearer {token}"} if token else {},
            )
            if r.status_code == 401:
                return []
            r.raise_for_status()
            return r.json().get("items", [])
    except Exception:  # noqa: BLE001
        return []


@st.cache_data(ttl=REFRESH_INTERVAL, show_spinner=False)
def fetch_drift_events(source_id: int, token: str = "") -> list[dict]:
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(
                API_DRIFT.format(source_id=source_id),
                params={"limit": 20},
                headers={"Authorization": f"Bearer {token}"} if token else {},
            )
            if r.status_code == 401:
                return []
            r.raise_for_status()
            return r.json().get("items", [])
    except Exception:  # noqa: BLE001
        return []


@st.cache_data(ttl=10, show_spinner=False)
def fetch_health_status() -> dict[str, dict]:
    """Probe /health and /readyz; return a dict of {endpoint: {status, code}}."""
    results: dict[str, dict] = {}
    for label, url in (
        ("liveness (/health)", API_HEALTH),
        ("readiness (/readyz)", API_READYZ),
    ):
        try:
            with httpx.Client(timeout=3.0) as client:
                r = client.get(url)
            results[label] = {"status_code": r.status_code, "body": r.json()}
        except Exception as exc:  # noqa: BLE001
            results[label] = {"status_code": None, "body": None, "error": str(exc)}
    return results


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
# Auth state
if "access_token" not in st.session_state:
    st.session_state["access_token"] = ""
if "refresh_token" not in st.session_state:
    st.session_state["refresh_token"] = ""
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "auth_username" not in st.session_state:
    st.session_state["auth_username"] = ""
# Agent panel state
if "agent_run_id" not in st.session_state:
    st.session_state["agent_run_id"] = ""
if "agent_result" not in st.session_state:
    st.session_state["agent_result"] = None
if "agent_hitl_paused" not in st.session_state:
    st.session_state["agent_hitl_paused"] = False
if "agent_stream_events" not in st.session_state:
    st.session_state["agent_stream_events"]: list[dict] = []

# ---------------------------------------------------------------------------
# Login sidebar
# ---------------------------------------------------------------------------


def _do_login(username: str, password: str) -> str | None:
    """POST /api/v1/auth/token (OAuth2 form). Returns error message or None."""
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.post(
                API_AUTH_TOKEN,
                data={"username": username, "password": password},
            )
            if r.status_code == 200:
                body = r.json()
                st.session_state["access_token"] = body["access_token"]
                st.session_state["refresh_token"] = body.get("refresh_token", "")
                st.session_state["logged_in"] = True
                st.session_state["auth_username"] = username
                return None
            return f"Login failed ({r.status_code}): {r.text[:120]}"
    except Exception as exc:  # noqa: BLE001
        return f"Connection error: {exc}"


def _do_refresh() -> bool:
    """POST /api/v1/auth/refresh. Rotates both tokens. Returns True on success."""
    rt = st.session_state.get("refresh_token", "")
    if not rt:
        return False
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.post(API_AUTH_REFRESH, json={"refresh_token": rt})
            if r.status_code == 200:
                body = r.json()
                st.session_state["access_token"] = body["access_token"]
                st.session_state["refresh_token"] = body.get("refresh_token", "")
                return True
    except Exception:  # noqa: BLE001  # nosec B110 — refresh failure: force logout path, pass is safe
        pass
    # Refresh failed — force logout
    st.session_state["access_token"] = ""
    st.session_state["refresh_token"] = ""
    st.session_state["logged_in"] = False
    return False


def _auth_headers() -> dict[str, str]:
    token = st.session_state.get("access_token", "")
    return {"Authorization": f"Bearer {token}"} if token else {}


with st.sidebar:
    st.header("Authentication")
    if not st.session_state["logged_in"]:
        with st.form("login_form"):
            _uname = st.text_input("Username")
            _pwd = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
                _err = _do_login(_uname, _pwd)
                if _err:
                    st.error(_err)
                else:
                    st.cache_data.clear()
                    st.rerun()
    else:
        st.success(f"Logged in as **{st.session_state['auth_username']}**")
        if st.button("Logout"):
            st.session_state["access_token"] = ""
            st.session_state["refresh_token"] = ""
            st.session_state["logged_in"] = False
            st.session_state["auth_username"] = ""
            st.cache_data.clear()
            st.rerun()

# ---------------------------------------------------------------------------
# Panel 1: Source Health
# ---------------------------------------------------------------------------

st.header("Source Health")

_token = st.session_state.get("access_token", "")
scorecards = fetch_scorecards(token=_token)

# 401 — silent token refresh then retry
if scorecards and scorecards[0].get("_401"):
    if _do_refresh():
        st.cache_data.clear()
        _token = st.session_state.get("access_token", "")
        scorecards = fetch_scorecards(token=_token)
    else:
        scorecards = []

if not st.session_state["logged_in"]:
    st.warning("Log in from the sidebar to view data.")
elif scorecards and "_error" in scorecards[0]:
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

sources = fetch_sources(token=_token)
if not sources:
    st.info("No sources registered yet.")
else:
    all_drift: list[dict] = []
    for src in sources:
        events = fetch_drift_events(src["id"], token=_token)
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
    "Receives `observation.created`, `drift.detected`, `job.progress`, and `ping` events."
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
    msg_container.markdown("\n\n".join(lines))


if st.session_state.ws_connected:
    import websockets as _ws  # type: ignore[import-untyped]

    # Capture thread-safe primitives by value — the closure must never touch
    # st.session_state because background threads have no ScriptRunContext.
    _stop: threading.Event = st.session_state["_ws_stop"]
    _buf: queue.Queue = st.session_state["_ws_buf"]
    _ws_token: str = st.session_state.get("access_token", "")
    _ws_url: str = (
        INGESTOR_URL.replace("http://", "ws://").replace("https://", "wss://")
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
# Panel 4: Agent Enrichment
# ---------------------------------------------------------------------------

st.header("🤖 Agent Enrichment")
st.caption(
    "Invoke the LangGraph enrichment agent against any observation. "
    "Choose full-auto, Human-in-the-Loop (HITL), or SSE streaming."
)

_agent_token = st.session_state.get("access_token", "")
_agent_headers = {"Authorization": f"Bearer {_agent_token}"} if _agent_token else {}

agent_tab_full, agent_tab_hitl, agent_tab_stream = st.tabs(
    ["⚡ Full Run", "👁 HITL Review", "📡 Stream (SSE)"]
)

# --- Tab 1: Full auto run ---
with agent_tab_full:
    col_rid, col_go = st.columns([2, 1])
    _full_rid = col_rid.number_input(
        "Observation ID", min_value=1, value=1, step=1, key="agent_full_rid"
    )
    if col_go.button("▶ Enrich", key="agent_full_run"):
        with st.spinner("Running enrichment agent…"):
            try:
                with httpx.Client(timeout=60.0) as _c:
                    _r = _c.post(
                        API_AGENT_ENRICH.format(observation_id=int(_full_rid)),
                        headers=_agent_headers,
                    )
                    _r.raise_for_status()
                    st.session_state["agent_result"] = _r.json()
                    st.session_state["agent_hitl_paused"] = False
            except Exception as _exc:  # noqa: BLE001
                st.error(f"Agent call failed: {_exc}")
    if st.session_state["agent_result"] and not st.session_state["agent_hitl_paused"]:
        _res = st.session_state["agent_result"]
        st.success(f"Run `{_res.get('run_id', '?')}` complete")
        _clf = _res.get("classification")
        if _clf:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Category", _clf.get("category", "—"))
            c2.metric("Priority", _clf.get("priority", "—"))
            c3.metric("Sentiment", _clf.get("sentiment", "—"))
            c4.metric("Published", "✅" if _res.get("published") else "⏸")
            st.markdown(f"**Summary:** {_clf.get('summary', '—')}")
        if _res.get("analysis"):
            with st.expander("Analysis", expanded=True):
                st.write(_res["analysis"])

# --- Tab 2: HITL review + resume ---
with agent_tab_hitl:
    col_hrid, col_hgo = st.columns([2, 1])
    _hitl_rid = col_hrid.number_input(
        "Observation ID", min_value=1, value=1, step=1, key="agent_hitl_rid"
    )
    if col_hgo.button("👁 Start Review", key="agent_hitl_start"):
        with st.spinner("Starting HITL enrichment…"):
            try:
                with httpx.Client(timeout=60.0) as _c:
                    _r = _c.post(
                        API_AGENT_REVIEW.format(observation_id=int(_hitl_rid)),
                        headers=_agent_headers,
                    )
                    _r.raise_for_status()
                    _body = _r.json()
                    st.session_state["agent_run_id"] = _body.get("run_id", "")
                    st.session_state["agent_result"] = _body
                    st.session_state["agent_hitl_paused"] = _body.get(
                        "hitl_paused", False
                    )
            except Exception as _exc:  # noqa: BLE001
                st.error(f"HITL call failed: {_exc}")

    if st.session_state["agent_hitl_paused"]:
        _res = st.session_state["agent_result"]
        st.warning(
            f"⏸ Paused before publish — Run ID: `{st.session_state['agent_run_id']}`"
        )
        _clf = _res.get("classification") if _res else None
        if _clf:
            c1, c2, c3 = st.columns(3)
            c1.metric("Category", _clf.get("category", "—"))
            c2.metric("Priority", _clf.get("priority", "—"))
            c3.metric("Sentiment", _clf.get("sentiment", "—"))
            st.markdown(f"**Summary:** {_clf.get('summary', '—')}")
        if _res and _res.get("analysis"):
            with st.expander("Analysis to publish", expanded=True):
                st.write(_res["analysis"])

        col_approve, col_reject = st.columns(2)
        if col_approve.button("✅ Approve & Publish", key="agent_hitl_approve"):
            with st.spinner("Resuming with approval…"):
                try:
                    with httpx.Client(timeout=60.0) as _c:
                        _r = _c.post(
                            API_AGENT_RESUME.format(
                                run_id=st.session_state["agent_run_id"]
                            ),
                            json={"approve": True},
                            headers=_agent_headers,
                        )
                        _r.raise_for_status()
                        st.session_state["agent_result"] = _r.json()
                        st.session_state["agent_hitl_paused"] = False
                        st.success("Published! ✅")
                        st.rerun()
                except Exception as _exc:  # noqa: BLE001
                    st.error(f"Resume failed: {_exc}")
        if col_reject.button("❌ Reject", key="agent_hitl_reject"):
            with st.spinner("Rejecting…"):
                try:
                    with httpx.Client(timeout=60.0) as _c:
                        _r = _c.post(
                            API_AGENT_RESUME.format(
                                run_id=st.session_state["agent_run_id"]
                            ),
                            json={"approve": False},
                            headers=_agent_headers,
                        )
                        _r.raise_for_status()
                        st.session_state["agent_result"] = None
                        st.session_state["agent_hitl_paused"] = False
                        st.info("Run rejected — publish skipped.")
                        st.rerun()
                except Exception as _exc:  # noqa: BLE001
                    st.error(f"Reject failed: {_exc}")

# --- Tab 3: SSE stream ---
with agent_tab_stream:
    col_srid, col_sgo = st.columns([2, 1])
    _stream_rid = col_srid.number_input(
        "Observation ID", min_value=1, value=1, step=1, key="agent_stream_rid"
    )
    if col_sgo.button("📡 Stream", key="agent_stream_run"):
        st.session_state["agent_stream_events"] = []
        _stream_url = API_AGENT_STREAM.format(observation_id=int(_stream_rid))
        _event_placeholder = st.empty()
        try:
            with httpx.Client(timeout=120.0) as _c:
                with _c.stream(
                    "GET",
                    _stream_url,
                    headers={**_agent_headers, "Accept": "text/event-stream"},
                ) as _resp:
                    _resp.raise_for_status()
                    _current_event = ""
                    for _line in _resp.iter_lines():
                        if _line.startswith("event:"):
                            _current_event = _line[len("event:") :].strip()
                        elif _line.startswith("data:"):
                            _raw = _line[len("data:") :].strip()
                            try:
                                _data = json.loads(_raw)
                            except json.JSONDecodeError:
                                _data = {"raw": _raw}
                            st.session_state["agent_stream_events"].append(
                                {"event": _current_event, **_data}
                            )
                            _event_placeholder.empty()
        except Exception as _exc:  # noqa: BLE001
            st.error(f"Stream error: {_exc}")

    if st.session_state["agent_stream_events"]:
        for _ev in st.session_state["agent_stream_events"]:
            _etype = _ev.get("event", "")
            _icon = {"node_complete": "🔵", "done": "✅", "error": "🔴"}.get(
                _etype, "📨"
            )
            if _etype == "node_complete":
                _node = _ev.get("node", "?")
                st.markdown(f"{_icon} **node_complete** → `{_node}`")
                if _ev.get("classification"):
                    st.json(_ev["classification"], expanded=False)
            elif _etype == "done":
                st.success(f"✅ Done — run `{_ev.get('run_id', '?')}`")
                if _ev.get("analysis"):
                    st.write(_ev["analysis"])
            elif _etype == "error":
                st.error(_ev.get("error", "Unknown error"))
    else:
        st.info("Press **Stream** to run and receive SSE events node-by-node.")

# ---------------------------------------------------------------------------
# Panel 5: Service Health
# ---------------------------------------------------------------------------

st.header("Service Health")
st.caption(
    "Live probe status for liveness (/health) and readiness (/readyz) endpoints."
)

col_probe, col_refresh_probe = st.columns([4, 1])
if col_refresh_probe.button("🔄 Re-check", key="health_recheck"):
    st.cache_data.clear()

health_data = fetch_health_status()
probe_cols = st.columns(len(health_data))
for col, (label, info) in zip(probe_cols, health_data.items(), strict=False):
    code = info.get("status_code")
    body = info.get("body") or {}
    err = info.get("error")
    if err:
        col.metric(label, "Error", delta=err, delta_color="inverse")
    elif code == 200:
        probe_status = body.get("status", "ok")
        col.metric(label, f"✅ {probe_status} ({code})")
    else:
        col.metric(
            label, f"🔴 degraded ({code})", delta="check logs", delta_color="inverse"
        )

    if body:
        checks = {k: v for k, v in body.items() if k not in ("status", "version")}
        if checks:
            col.json(checks, expanded=False)

st.caption(
    f"Prometheus metrics are scraped from [`{API_METRICS}`]({API_METRICS}) — "
    "open in a browser to view the raw exposition format."
)

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
