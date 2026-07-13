"""Panel: Service Health checks.

Split into:
  - ``use_*`` — data-fetching hooks
  - ``render_*`` — pure display from pre-fetched data
"""

from __future__ import annotations

from services.dashboard.core.api_client import api
from services.dashboard.core.auth import AuthManager
from services.dashboard.ui.protocols import UIAdapter


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


def use_service_health() -> dict:
    return {"health_data": api.health.probes()}


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def render_service_health(ui: UIAdapter, auth: AuthManager) -> None:
    """Render the service health panel with liveness/readiness probes."""
    ui.header("Service Health")
    ui.caption(
        "Live probe status for liveness (/health) and readiness (/readyz) endpoints."
    )

    col_probe, col_refresh_probe = ui.columns([4, 1])
    if col_refresh_probe.button("🔄 Re-check", key="health_recheck"):
        ui.clear_cache()

    data = use_service_health()
    health_data = data["health_data"]
    probe_cols = ui.columns(len(health_data))

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
                label,
                f"🔴 degraded ({code})",
                delta="check logs",
                delta_color="inverse",
            )

        if body:
            checks = {k: v for k, v in body.items() if k not in ("status", "version")}
            if checks:
                col.json(checks, expanded=False)
