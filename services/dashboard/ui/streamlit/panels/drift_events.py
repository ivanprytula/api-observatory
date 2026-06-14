"""Panel 3: Drift Events table."""

from __future__ import annotations

from typing import Any

from services.dashboard.core.api_client import (
    DashboardApiError,
    fetch_drift_events,
    fetch_sources,
)
from services.dashboard.core.auth import AuthManager
from services.dashboard.ui.protocols import UIAdapter


def render_drift_events(ui: UIAdapter, auth: AuthManager) -> None:
    """Render the drift events table across all sources."""
    ui.header("Drift Events")

    try:
        sources = fetch_sources(auth=auth)
    except DashboardApiError:
        ui.show_info("Could not fetch sources.")
        return

    if not sources:
        ui.show_info("No sources registered yet.")
        return

    all_drift: list[dict[str, Any]] = []
    for src in sources:
        try:
            events = fetch_drift_events(src.id, auth=auth)
            for ev in events:
                all_drift.append(
                    {
                        "Source": src.name,
                        "Detected": ev.created_at.isoformat()[:19].replace("T", " "),
                        "Type": ev.event_type,
                        "Severity": ev.severity,
                        "Score": f"{ev.compatibility_score:.1f}",
                        "Summary": ev.summary or "—",
                    }
                )
        except DashboardApiError:
            pass

    # Sort newest first
    all_drift.sort(key=lambda r: r["Detected"], reverse=True)

    if not all_drift:
        ui.show_info("No drift events detected yet.")
        return

    severity_icon = {
        "critical": "🔴",
        "high": "🟠",
        "medium": "🟡",
        "low": "🔵",
        "none": "⚪",
    }
    for row in all_drift:
        row["Severity"] = f"{severity_icon.get(row['Severity'], '')} {row['Severity']}"

    ui.render_dataframe(all_drift[:50], width="stretch")
