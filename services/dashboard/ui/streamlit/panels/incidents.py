"""Panel: actionable dependency incident lifecycle."""

from __future__ import annotations

import httpx

from services.dashboard.core.api_client import DashboardApiError, api
from services.dashboard.core.auth import AuthManager
from services.dashboard.ui.protocols import UIAdapter


def _friendly_api_error(exc: Exception) -> str:
    """Return a compact, user-facing error string."""
    if isinstance(exc, DashboardApiError):
        return str(exc)
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            detail = exc.response.json().get("detail", exc.response.text)
        except Exception:
            detail = exc.response.text
        return f"API error ({exc.response.status_code}): {detail}"
    return f"Unexpected error: {exc}"


def _incident_actions(ui: UIAdapter, auth: AuthManager, incident) -> None:
    """Render acknowledge / resolve buttons based on current status."""
    status = (incident.status or "").lower()
    iid = incident.id

    if status == "open":
        if ui.button("Acknowledge", key=f"inc_ack_{iid}"):
            try:
                api.incidents.acknowledge(incident_id=iid, token=auth.access_token)
                ui.show_success(f"Incident #{iid} acknowledged.")
                ui.rerun()
            except (httpx.HTTPStatusError, DashboardApiError) as exc:
                ui.show_error(f"Acknowledge failed: {_friendly_api_error(exc)}")

    elif status == "acknowledged":
        col_a, col_r = ui.columns(2)
        if col_a.button("Resolve", key=f"inc_res_{iid}"):
            try:
                api.incidents.resolve(incident_id=iid, token=auth.access_token)
                ui.show_success(f"Incident #{iid} resolved.")
                ui.rerun()
            except (httpx.HTTPStatusError, DashboardApiError) as exc:
                ui.show_error(f"Resolve failed: {_friendly_api_error(exc)}")
        if col_r.button("Reopen", key=f"inc_reopen_{iid}", disabled=True):
            pass  # Placeholder if reopen endpoint is added later.


def render_incidents(ui: UIAdapter, auth: AuthManager) -> None:
    """Render current tenant incidents with guidance and lifecycle state."""
    ui.header("Dependency Incidents")
    try:
        response = api.incidents.list(token=auth.access_token, limit=50)
    except (httpx.HTTPStatusError, DashboardApiError) as exc:
        ui.show_warning(f"Incident data unavailable: {_friendly_api_error(exc)}")
        return

    if not response.items:
        ui.show_info("No dependency incidents recorded yet.")
        return

    for incident in response.items:
        with ui.container():
            status = (incident.status or "unknown").lower()
            status_icon = {
                "open": "🔴",
                "acknowledged": "🟠",
                "resolved": "🟢",
            }.get(status, "⚪")

            ui.markdown(
                f"**#{incident.id}** {status_icon} **{status.upper()}** — "
                f"{incident.trigger_type} | severity: {incident.severity} | "
                f"occurrences: {incident.occurrence_count}"
            )
            ui.caption(f"Last seen: {incident.last_seen_at.isoformat()[:19]}")
            ui.markdown(f"**Summary:** {incident.summary}")
            if incident.guidance:
                ui.markdown(f"**Guidance:** {incident.guidance}")
            if incident.acknowledged_by:
                ack_ts = (
                    incident.acknowledged_at.isoformat()[:19]
                    if incident.acknowledged_at
                    else "—"
                )
                ui.caption(f"Acknowledged by {incident.acknowledged_by} at {ack_ts}")
            if incident.resolved_by:
                res_ts = (
                    incident.resolved_at.isoformat()[:19]
                    if incident.resolved_at
                    else "—"
                )
                ui.caption(f"Resolved by {incident.resolved_by} at {res_ts}")

            _incident_actions(ui, auth, incident)
        ui.divider()
