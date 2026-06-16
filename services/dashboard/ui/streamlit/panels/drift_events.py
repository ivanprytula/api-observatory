"""Panel: Drift Events — schema contract changes per source.

Split into:
  - ``use_*`` — data-fetching hooks
  - ``render_*`` — pure display from pre-fetched data
"""

from __future__ import annotations

from services.dashboard.core.api_client import (
    DashboardApiError,
    api,
)
from services.dashboard.core.auth import AuthManager
from services.dashboard.ui.protocols import UIAdapter


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


def use_drift_events(token: str = "") -> dict:
    try:
        sources = api.sources.list(token=token)
    except DashboardApiError:
        sources = []

    events: list[dict] = []
    for src in sources:
        try:
            evts = api.drift.list(source_id=src.id, token=token)
            for e in evts:
                events.append(
                    {
                        "source_name": src.name,
                        "severity": e.severity,
                        "event_type": e.event_type,
                        "compatibility_score": e.compatibility_score,
                        "summary": e.summary or "",
                        "created_at": e.created_at.isoformat()[:19]
                        if e.created_at
                        else "—",
                        "added_fields": len(e.added_fields or []),
                        "removed_fields": len(e.removed_fields or []),
                    }
                )
        except DashboardApiError:
            pass

    events.sort(key=lambda x: x["created_at"], reverse=True)
    return {"events": events}


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def render_drift_events(ui: UIAdapter, auth: AuthManager) -> None:
    """Render all drift events across sources."""
    ui.header("Drift Events")

    data = use_drift_events(token=auth.access_token)
    events = data["events"]

    if not events:
        ui.show_info("No drift events detected yet.")
        return

    rows = []
    for ev in events:
        severity_icon = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
        }.get(ev["severity"], "⚪")
        rows.append(
            {
                "Source": ev["source_name"],
                "Event": ev["event_type"],
                f"{severity_icon} Severity": ev["severity"],
                "Score": (
                    f"{ev['compatibility_score']:.1f}"
                    if ev["compatibility_score"] is not None
                    else "—"
                ),
                "Summary": ev["summary"][:60] if ev["summary"] else "—",
                "Fields ±": f"+{ev['added_fields']}/-{ev['removed_fields']}",
                "Time": ev["created_at"],
            }
        )

    ui.render_dataframe(rows, width="stretch")
