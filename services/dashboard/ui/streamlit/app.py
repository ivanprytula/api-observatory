"""Streamlit dashboard entry point.

Refactored to use framework-agnostic core modules and UI panels.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import streamlit as st
from services.dashboard.core.config import config
from services.dashboard.ui.streamlit.adapter import StreamlitUIAdapter
from services.dashboard.ui.streamlit.components.auth_sidebar import render_auth_sidebar
from services.dashboard.ui.streamlit.panels.agent_enrichment import (
    render_agent_enrichment,
)
from services.dashboard.ui.streamlit.panels.drift_events import render_drift_events
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
from streamlit.errors import StreamlitSecretNotFoundError


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
    st.caption(f"Ingestor: `{config.ingestor_url}`")

    # Initialize UI adapter and auth manager
    ui = StreamlitUIAdapter()
    manager = ui.auth_manager_from_session()

    # Auto-login from secrets.toml if available and not already logged in
    if not manager.state.logged_in:
        try:
            auth = st.secrets.get("auth", {})
        except StreamlitSecretNotFoundError:
            auth = {}
        if auth:
            username = auth.get("username")
            password = auth.get("password")
            if username and password:
                error = manager.do_login(username, password)
                if not error:
                    ui.sync_auth_to_session(manager)

    # Render auth sidebar
    render_auth_sidebar(ui, manager)

    # Refresh token on 401
    if manager.state.logged_in and manager.state.refresh_token:
        manager.do_refresh()
        ui.sync_auth_to_session(manager)

    # Render panels
    render_source_health_table(ui, manager)
    render_ingestion_throughput(ui)
    render_probe_scheduler(ui, manager)
    render_freshness_heatmap(ui, manager)
    render_drift_events(ui, manager)
    render_observations_panel(ui, manager)
    render_live_stream(ui, manager)
    render_agent_enrichment(ui, manager)
    render_service_health(ui, manager)
    render_queue_retry_health(ui, manager)

    # Refresh footer
    st.divider()
    col_r, col_auto = st.columns([3, 1])
    col_r.caption(
        f"Data last fetched from `{config.ingestor_url}` — cache TTL {config.refresh_interval}s"
    )
    if col_auto.button("🔄 Refresh now"):
        st.cache_data.clear()
        st.session_state.last_refresh = time.time()
        st.rerun()


if __name__ == "__main__":
    main()
