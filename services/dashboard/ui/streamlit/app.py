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
    st.caption(f"Ingestor: `{config.ingestor_url}`")

    ui = StreamlitUIAdapter()
    manager = ui.auth_manager_from_session()

    render_auth_sidebar(ui, manager)

    if (
        manager.state.logged_in
        and manager.state.refresh_token
        and not manager.state.is_valid
    ):
        manager.do_refresh()

    render_onboarding_guide(ui, manager)

    render_source_manager(ui, manager)
    render_source_health_table(ui, manager)
    render_ingestion_throughput(ui)
    render_probe_scheduler(ui, manager)
    render_freshness_heatmap(ui, manager)
    render_drift_events(ui, manager)
    render_incidents(ui, manager)
    render_observations_panel(ui, manager)
    render_live_stream(ui, manager)
    render_service_health(ui, manager)
    render_queue_retry_health(ui, manager)

    st.divider()
    col_r, col_auto = st.columns([3, 1])
    col_r.caption(
        f"Data last fetched from `{config.ingestor_url}` — cache TTL {config.refresh_interval}s"
    )
    if col_auto.button("🔄 Refresh now"):
        st.cache_data.clear()
        st.session_state.last_refresh = time.time()
        st.rerun()


def render_onboarding_guide(ui: StreamlitUIAdapter, manager) -> None:
    """Collapsible getting-started guide with auto-completing steps."""
    with st.expander("🚀 Getting Started", expanded=not manager.state.logged_in):
        st.markdown("Follow these steps to start using the API Observatory:")
        logged_in = manager.state.logged_in

        col1, col2, col3 = st.columns([1, 4, 2])
        col1.markdown("1. **Log in**")
        if logged_in:
            col2.success("✅ Done")
        else:
            col2.warning("⏳ Pending")
        col3.markdown("Enter credentials in the sidebar")

        col1.markdown("2. **Add sources**")
        col2.info("⏸ Next")
        col3.markdown("Add source URLs in the *Source Manager* section below")

        col1.markdown("3. **Run probes**")
        col2.info("⏸ Next")
        col3.markdown("Click *Probe All* in the Probe Scheduler section")

        col1.markdown("4. **Explore data**")
        col2.info("⏸ Next")
        col3.markdown("View observations, drift events, and health metrics")


if __name__ == "__main__":
    main()
