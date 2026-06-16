"""Panel 1: Source Health table and freshness heatmap."""

from __future__ import annotations

from datetime import UTC, datetime

from services.dashboard.core.api_client import (
    DashboardApiError,
    cached_fetch_scorecards,
    fetch_prometheus_metrics,
    fetch_sources,
)
from services.dashboard.core.auth import AuthManager
from services.dashboard.core.metrics_parser import (
    parse_metric_value,
    parse_prometheus_counter,
)
from services.dashboard.ui.protocols import UIAdapter


def render_source_health_table(
    ui: UIAdapter, auth: AuthManager, metrics_text: str = ""
) -> None:
    """Render the source health scorecard table."""
    try:
        # Use cached version with auth token for 60-second TTL
        scorecards_resp = cached_fetch_scorecards(token=auth.access_token)
        scorecards = scorecards_resp.items
        if not scorecards:
            ui.show_info(
                "No scorecards yet — seed some sources and wait for the first probe cycle."
            )
            return
        rows = []
        for sc in scorecards:
            uptime = sc.uptime_pct
            p95 = sc.p95_latency_ms
            burn = sc.error_budget_burn_rate
            status = (
                "🟢" if (uptime or 0) >= 99 else ("🟡" if (uptime or 0) >= 95 else "🔴")
            )
            rows.append(
                {
                    "Source ID": sc.source_id,
                    "Uptime %": f"{uptime:.1f}" if uptime is not None else "—",
                    "p95 Latency ms": f"{p95:.0f}" if p95 is not None else "—",
                    "Error Budget Burn": f"{burn:.2f}x" if burn is not None else "—",
                    "Status": status,
                }
            )
        ui.render_dataframe(rows, width="stretch")
    except DashboardApiError as e:
        if e.status_code == 401:
            ui.show_warning("Log in from the sidebar to view data.")
        else:
            ui.show_error(f"Could not reach ingestor: {e}")
    except Exception as exc:  # noqa: BLE001
        ui.show_error(f"Error loading scorecards: {exc}")


def render_ingestion_throughput(ui: UIAdapter, metrics_text: str = "") -> None:
    """Render ingestion metrics: observations received, queue lag, backfill batches."""
    try:
        metrics = metrics_text if metrics_text else fetch_prometheus_metrics()
    except DashboardApiError:
        metrics = ""

    observe_total = parse_prometheus_counter(metrics, "observations_received_total")
    event_lag = parse_metric_value(metrics, "ingestion_queue_lag") or 0
    backfill_total = parse_prometheus_counter(metrics, "backfill_batches_total")

    c1, c2, c3 = ui.columns(3)
    c1.metric("Observations received (total)", f"{observe_total:,.0f}")
    c2.metric("Queue lag", f"{event_lag:,.0f}")
    c3.metric("Backfill batches (total)", f"{backfill_total:,.0f}")


def render_freshness_heatmap(
    ui: UIAdapter, auth: AuthManager, metrics_text: str = ""
) -> None:
    """Render Source Freshness heatmap-style table showing drift minutes."""
    try:
        sources = fetch_sources(auth=auth)
    except DashboardApiError as e:
        if e.status_code == 401:
            ui.show_info("Log in and seed sources to view freshness heatmap.")
            return
        ui.show_error(f"Could not fetch sources: {e}")
        return

    if not sources:
        ui.show_info("No sources registered yet.")
        return

    now_ts = datetime.now(UTC).timestamp()
    rows = []
    for src in sources:
        last = src.updated_at or src.created_at
        drift_minutes = None
        if last:
            try:
                if isinstance(last, str):
                    ts_raw = last.replace("Z", "+00:00")
                    drift_minutes = (
                        datetime.fromisoformat(ts_raw).timestamp() - now_ts
                    ) / 60.0
                else:
                    drift_minutes = (now_ts - last.timestamp()) / 60.0
            except Exception:  # noqa: BLE001
                drift_minutes = None

        if drift_minutes is None:
            badge = "⚪ unknown"
        elif drift_minutes <= 5:
            badge = "🟢 fresh"
        elif drift_minutes <= 30:
            badge = "🟡 aging"
        else:
            badge = "🔴 stale"

        if hasattr(last, "isoformat"):
            last_str = last.isoformat()[:19]  # type: ignore[union-attr]
        elif last:
            last_str = str(last)[:19]
        else:
            last_str = "—"
        last_display = (
            last_str.replace("T", " ") if last_str and "T" in last_str else last_str
        )
        rows.append(
            {
                "Source": src.name,
                "Last probe": last_display,
                "Drift (min)": f"{drift_minutes:.1f}"
                if drift_minutes is not None
                else "—",
                "Status": badge,
            }
        )

    ui.render_dataframe(rows, width="stretch")
