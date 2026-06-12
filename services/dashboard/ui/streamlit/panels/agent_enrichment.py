"""Panel 4: Agent Enrichment (LangGraph agent integration)."""

from __future__ import annotations

import json

import httpx

from services.dashboard.core.api_client import (
    DashboardApiError,
    agent_enrich,
    agent_resume,
    agent_start_hitl,
)
from services.dashboard.core.auth import AuthManager
from services.dashboard.core.config import config
from services.dashboard.ui.protocols import UIAdapter


def render_agent_enrichment(ui: UIAdapter, auth: AuthManager) -> None:
    """Render the agent enrichment panel with full auto, HITL, and SSE modes."""
    ui.header("🤖 Agent Enrichment")
    ui.caption(
        "Invoke the LangGraph enrichment agent against any observation. "
        "Choose full-auto, Human-in-the-Loop (HITL), or SSE streaming."
    )

    agent_tab_full, agent_tab_hitl, agent_tab_stream = ui.tabs(
        ["⚡ Full Run", "👁 HITL Review", "📡 Stream (SSE)"]
    )

    _agent_headers = auth.auth_headers

    # --- Tab 1: Full auto run ---
    with agent_tab_full:
        col_rid, col_go = ui.columns([2, 1])
        full_rid = col_rid.number_input(
            "Observation ID", min_value=1, value=1, step=1, key="agent_full_rid"
        )
        if col_go.button("▶ Enrich", key="agent_full_run"):
            with ui.spinner("Running enrichment agent…"):
                try:
                    result = agent_enrich(int(full_rid), auth=auth)
                    ui.agent_result = result
                    ui.agent_hitl_paused = False
                except DashboardApiError as exc:
                    ui.show_error(f"Agent call failed: {exc}")

        if ui.agent_result and not ui.agent_hitl_paused:
            res = ui.agent_result
            ui.show_success(f"Run `{res.get('run_id', '?')}` complete")
            clf = res.get("classification")
            if clf:
                c1, c2, c3, c4 = ui.columns(4)
                c1.metric("Category", clf.get("category", "—"))
                c2.metric("Priority", clf.get("priority", "—"))
                c3.metric("Sentiment", clf.get("sentiment", "—"))
                c4.metric("Published", "✅" if res.get("published") else "⏸")
                ui.markdown(f"**Summary:** {clf.get('summary', '—')}")
            if res.get("analysis"):
                with ui.expander("Analysis", expanded=True):
                    ui.write(res["analysis"])

    # --- Tab 2: HITL review + resume ---
    with agent_tab_hitl:
        col_hrid, col_hgo = ui.columns([2, 1])
        hitl_rid = col_hrid.number_input(
            "Observation ID", min_value=1, value=1, step=1, key="agent_hitl_rid"
        )
        if col_hgo.button("👁 Start Review", key="agent_hitl_start"):
            with ui.spinner("Starting HITL enrichment…"):
                try:
                    body = agent_start_hitl(int(hitl_rid), auth=auth)
                    ui.agent_run_id = body.get("run_id", "")
                    ui.agent_result = body
                    ui.agent_hitl_paused = body.get("hitl_paused", False)
                except DashboardApiError as exc:
                    ui.show_error(f"HITL call failed: {exc}")

        if ui.agent_hitl_paused:
            res = ui.agent_result
            ui.show_warning(f"⏸ Paused before publish — Run ID: `{ui.agent_run_id}`")
            clf = res.get("classification") if res else None
            if clf:
                c1, c2, c3 = ui.columns(3)
                c1.metric("Category", clf.get("category", "—"))
                c2.metric("Priority", clf.get("priority", "—"))
                c3.metric("Sentiment", clf.get("sentiment", "—"))
                ui.markdown(f"**Summary:** {clf.get('summary', '—')}")
            if res and res.get("analysis"):
                with ui.expander("Analysis to publish", expanded=True):
                    ui.write(res["analysis"])

            col_approve, col_reject = ui.columns(2)
            if col_approve.button("✅ Approve & Publish", key="agent_hitl_approve"):
                with ui.spinner("Resuming with approval…"):
                    try:
                        result = agent_resume(ui.agent_run_id, True, auth=auth)
                        ui.agent_result = result
                        ui.agent_hitl_paused = False
                        ui.show_success("Published! ✅")
                        ui.rerun()
                    except DashboardApiError as exc:
                        ui.show_error(f"Resume failed: {exc}")
            if col_reject.button("❌ Reject", key="agent_hitl_reject"):
                with ui.spinner("Rejecting…"):
                    try:
                        agent_resume(ui.agent_run_id, False, auth=auth)
                        ui.agent_result = None
                        ui.agent_hitl_paused = False
                        ui.show_info("Run rejected — publish skipped.")
                        ui.rerun()
                    except DashboardApiError as exc:
                        ui.show_error(f"Reject failed: {exc}")

    # --- Tab 3: SSE stream ---
    with agent_tab_stream:
        col_srid, col_sgo = ui.columns([2, 1])
        stream_rid = col_srid.number_input(
            "Observation ID", min_value=1, value=1, step=1, key="agent_stream_rid"
        )
        if col_sgo.button("📡 Stream", key="agent_stream_run"):
            ui.agent_stream_events = []
            stream_url = (
                f"{config.api_base_url}/api/v1/agent/enrich/{int(stream_rid)}/stream"
            )
            event_placeholder = ui.empty()
            try:
                with httpx.Client(timeout=120.0) as _c:
                    with _c.stream(
                        "GET",
                        stream_url,
                        headers={**auth.auth_headers, "Accept": "text/event-stream"},
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
                                ui.agent_stream_events.append(
                                    {"event": _current_event, **_data}
                                )
                                event_placeholder.empty()
            except Exception as exc:  # noqa: BLE001
                ui.show_error(f"Stream error: {exc}")

        if ui.agent_stream_events:
            for ev in ui.agent_stream_events:
                etype = ev.get("event", "")
                icon = {"node_complete": "🔵", "done": "✅", "error": "🔴"}.get(
                    etype, "📨"
                )
                if etype == "node_complete":
                    node = ev.get("node", "?")
                    ui.markdown(f"{icon} **node_complete** → `{node}`")
                    if ev.get("classification"):
                        ui.json(ev["classification"], expanded=False)
                elif etype == "done":
                    ui.show_success(f"✅ Done — run `{ev.get('run_id', '?')}`")
                    if ev.get("analysis"):
                        ui.write(ev["analysis"])
                elif etype == "error":
                    ui.show_error(ev.get("error", "Unknown error"))
        else:
            ui.show_info("Press **Stream** to run and receive SSE events node-by-node.")
