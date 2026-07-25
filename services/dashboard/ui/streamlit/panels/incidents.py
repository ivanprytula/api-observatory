"""Panel: actionable dependency incident lifecycle."""

from __future__ import annotations

import httpx

from services.dashboard.core.api_client import DashboardApiError, api
from services.dashboard.core.auth import AuthManager
from services.dashboard.ui.protocols import UIAdapter


def render_incidents(ui: UIAdapter, auth: AuthManager) -> None:
    """Render current tenant incidents with guidance and lifecycle state."""
    ui.header("Dependency Incidents")
    try:
        response = api.incidents.list(token=auth.access_token, limit=50)
    except (httpx.HTTPStatusError, DashboardApiError) as exc:
        ui.show_warning(f"Incident data unavailable: {exc}")
        return

    if not response.items:
        ui.show_info("No dependency incidents recorded yet.")
        return

    rows = []
    for incident in response.items:
        rows.append(
            {
                "ID": incident.id,
                "Source": incident.source_id,
                "Trigger": incident.trigger_type,
                "Status": incident.status,
                "Severity": incident.severity,
                "Occurrences": incident.occurrence_count,
                "Summary": incident.summary,
                "Guidance": incident.guidance,
                "Last seen": incident.last_seen_at.isoformat()[:19],
            }
        )
    ui.render_dataframe(rows, width="stretch")
