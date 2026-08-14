"""Streamlit dashboard entry point.

Refactored to use framework-agnostic core modules and UI panels.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
from services.dashboard.ui.streamlit.adapter import StreamlitUIAdapter
from services.dashboard.ui.streamlit.components.auth_sidebar import render_auth_sidebar
from services.dashboard.ui.streamlit.panels.drift_events import render_drift_events
from services.dashboard.ui.streamlit.panels.incidents import render_incidents
from services.dashboard.ui.streamlit.panels.live_stream import render_live_stream
from services.dashboard.ui.streamlit.panels.observations import (
    render_observations_panel,
)
from services.dashboard.ui.streamlit.panels.probe_scheduler import (
    render_probe_scheduler,
    render_queue_retry_health,
)
from services.dashboard.ui.streamlit.panels.service_health import render_service_health
from services.dashboard.ui.streamlit.panels.source_health import (
    render_freshness_heatmap,
    render_ingestion_throughput,
    render_source_health_table,
)
from services.dashboard.ui.streamlit.panels.source_manager import render_source_manager


_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def main() -> None:
    """Main entry point for the Streamlit dashboard."""
    st.set_page_config(
        page_title="API Observatory",
        page_icon="🔭",
        layout="wide",
        initial_sidebar_state="auto",
    )

    st.title("🔭 API Observatory")

    if st.button("↻ Refresh"):
        st.cache_data.clear()
        st.rerun()

    ui = StreamlitUIAdapter()
    manager = ui.auth_manager_from_session()

    render_auth_sidebar(ui, manager)

    if (
        manager.state.logged_in
        and manager.state.refresh_token
        and not manager.state.is_valid
    ):
        refreshed = manager.do_refresh()
        if not refreshed:
            st.warning("Session expired — please log in again.")

    features = ui.fetch_stack_features()
    render_onboarding_guide(ui, manager, features)

    cache_status = features.get("cache_status", "unknown")
    websocket_status = features.get("websocket_status", "unknown")
    live_enabled = features.get("cache", False) and features.get("websocket", False)
    if not live_enabled:
        parts = []
        if not features.get("cache", False):
            if cache_status == "not_configured":
                parts.append("Redis cache is not enabled")
            elif cache_status == "unreachable":
                parts.append("Redis cache is unreachable")
            else:
                parts.append("Redis cache status is unknown")
        if not features.get("websocket", False):
            if websocket_status == "disabled":
                parts.append("WebSocket endpoint is disabled")
            elif websocket_status != "enabled":
                parts.append("WebSocket status is unknown")
        if parts:
            st.info("Live Stream disabled: " + " and ".join(parts) + ".")
    if not features.get("has_sources", False):
        st.info(
            "No sources yet. Add a source to unlock probes, observations, and health data."
        )

    ui.subheader("Sources")
    render_source_manager(ui, manager)

    ui.subheader("Probes")
    render_probe_scheduler(ui, manager)
    render_queue_retry_health(ui, manager)

    ui.subheader("Observations")
    render_observations_panel(ui, manager)
    render_drift_events(ui, manager)
    render_incidents(ui, manager)
    if features.get("cache", False) and features.get("websocket", False):
        render_live_stream(ui, manager)

    ui.subheader("Health")
    render_source_health_table(ui, manager)
    render_ingestion_throughput(ui)
    render_freshness_heatmap(ui, manager)
    render_service_health(ui, manager)


def render_onboarding_guide(ui: StreamlitUIAdapter, manager, features: dict) -> None:
    """Simplified getting-started checklist."""
    with st.expander("Getting Started", expanded=not manager.state.logged_in):
        logged_in = manager.state.logged_in
        has_sources = features.get("has_sources", False)
        has_observations = features.get("has_observations", False)

        steps = [
            ("Log in", "Done" if logged_in else "Enter credentials in the sidebar"),
            ("Add sources", "Done" if has_sources else "Add source URLs below"),
            ("Run probes", "Done" if has_observations else "Use Probe All below"),
            (
                "Explore data",
                "View observations, drift events, and health metrics",
            ),
        ]
        for label, status in steps:
            st.markdown(f"**{label}** — {status}")


if __name__ == "__main__":
    main()
