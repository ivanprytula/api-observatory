"""Streamlit panel components — use_* (fetch) + render_* (display) split."""

from services.dashboard.ui.streamlit.panels.drift_events import (
    render_drift_events,
    use_drift_events,
)
from services.dashboard.ui.streamlit.panels.live_stream import (
    render_live_stream,
    use_ws_connection,
)
from services.dashboard.ui.streamlit.panels.observations import (
    render_observations_panel,
    use_observation_detail,
    use_observations_page,
)
from services.dashboard.ui.streamlit.panels.probe_scheduler import (
    render_probe_scheduler,
    render_queue_retry_health,
    use_queue_retry_metrics,
)
from services.dashboard.ui.streamlit.panels.probe_scheduler import (
    use_sources as use_probe_sources,
)
from services.dashboard.ui.streamlit.panels.service_health import (
    render_service_health,
    use_service_health,
)
from services.dashboard.ui.streamlit.panels.source_health import (
    render_freshness_heatmap,
    render_ingestion_throughput,
    render_source_health_table,
    use_freshness_heatmap,
    use_ingestion_throughput,
    use_source_health_table,
)
from services.dashboard.ui.streamlit.panels.source_manager import (
    render_source_manager,
    use_source_by_id,
)
from services.dashboard.ui.streamlit.panels.source_manager import (
    use_sources as use_manager_sources,
)


__all__ = [
    "render_drift_events",
    "render_freshness_heatmap",
    "render_ingestion_throughput",
    "render_live_stream",
    "render_probe_scheduler",
    "render_queue_retry_health",
    "render_service_health",
    "render_source_health_table",
    "render_source_manager",
    "render_observations_panel",
    # hooks
    "use_drift_events",
    "use_freshness_heatmap",
    "use_ingestion_throughput",
    "use_manager_sources",
    "use_observation_detail",
    "use_observations_page",
    "use_probe_sources",
    "use_queue_retry_metrics",
    "use_service_health",
    "use_source_by_id",
    "use_source_health_table",
    "use_ws_connection",
]
