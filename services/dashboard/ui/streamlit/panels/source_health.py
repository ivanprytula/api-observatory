"""Panel 1: Source Health table + freshness heatmap + ingestion throughput.

Split into:
  - ``use_*`` —  data-fetching hooks (returns dict, no side-effects)
  - ``render_*`` — pure display from pre-fetched data
  - Legacy ``render_*`` (ui, auth) — backward-compatible combined call
"""

from __future__ import annotations

from datetime import UTC, datetime

from services.dashboard.core.api_client import (
    API_REQUEST_ERRORS,
    DashboardApiError,
    api,
    fetch_prometheus_metrics,
)
from services.dashboard.core.auth import AuthManager
from services.dashboard.core.metrics_parser import (
    parse_metric_value,
    parse_prometheus_counter,
)
from services.dashboard.ui.protocols import UIAdapter


# ---------------------------------------------------------------------------
# Hooks (data fetching, no UI)
# ---------------------------------------------------------------------------


def use_source_health_table(token: str = "") -> dict:
    try:
        scorecards_resp = api.scorecards.list(token=token)
    except API_REQUEST_ERRORS:
        return {"scorecards": []}
    return {"scorecards": scorecards_resp.items if scorecards_resp else []}


def use_ingestion_throughput() -> dict:
    try:
        metrics = fetch_prometheus_metrics()
    except DashboardApiError:
        metrics = ""
    return {
        "observations_received": parse_prometheus_counter(
            metrics, "observations_received_total"
        ),
        "queue_lag": parse_metric_value(metrics, "ingestion_queue_lag") or 0,
        "backfill_batches": parse_prometheus_counter(metrics, "backfill_batches_total"),
    }


def use_freshness_heatmap(token: str = "") -> dict:
    try:
        sources = api.sources.list(token=token)
    except API_REQUEST_ERRORS:
        sources = []
    try:
        jobs = api.health.scheduler_jobs().get("jobs", {})
    except API_REQUEST_ERRORS:
        jobs = {}
    return {"sources": sources, "jobs": jobs}


# ---------------------------------------------------------------------------
# Pure renderers (pre-fetched data)
# ---------------------------------------------------------------------------


def render_source_health_table(
    ui: UIAdapter, auth: AuthManager, metrics_text: str = ""
) -> None:
    data = use_source_health_table(token=auth.access_token)
    scorecards = data["scorecards"]
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


def render_ingestion_throughput(ui: UIAdapter, metrics_text: str = "") -> None:
    data = (
        use_ingestion_throughput()
        if not metrics_text
        else _parse_metrics_text(metrics_text)
    )
    c1, c2, c3 = ui.columns(3)
    c1.metric(
        "Observations received (total)",
        f"{data['observations_received']:,.0f}",
        help="Total API observations ingested since the service started.",
    )
    c2.metric(
        "Queue lag",
        f"{data['queue_lag']:,.0f}",
        help="Number of observations waiting in the ingestion queue.",
    )
    c3.metric(
        "Backfill batches (total)",
        f"{data['backfill_batches']:,.0f}",
        help="Number of historical data batches reprocessed.",
    )


def _parse_metrics_text(metrics_text: str) -> dict:
    return {
        "observations_received": parse_prometheus_counter(
            metrics_text, "observations_received_total"
        ),
        "queue_lag": parse_metric_value(metrics_text, "ingestion_queue_lag") or 0,
        "backfill_batches": parse_prometheus_counter(
            metrics_text, "backfill_batches_total"
        ),
    }


def render_freshness_heatmap(
    ui: UIAdapter, auth: AuthManager, metrics_text: str = ""
) -> None:
    data = use_freshness_heatmap(token=auth.access_token)
    sources = data["sources"]
    jobs = data.get("jobs", {})
    if not sources:
        ui.show_info("No sources registered yet.")
        return

    now_ts = datetime.now(UTC).timestamp()
    rows = []
    for src in sources:
        # Prefer the scheduler's actual last probe execution over the source
        # profile's own updated_at, which only changes when the registration
        # record itself is edited (name, interval, etc.) — not on each probe.
        job = jobs.get(f"probe_source_{src.id}", {})
        last = job.get("last_run_at") or src.updated_at or src.created_at
        drift_minutes = None
        if last:
            try:
                if isinstance(last, str):
                    ts_raw = last.replace("Z", "+00:00")
                    parsed = datetime.fromisoformat(ts_raw)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=UTC)
                    drift_minutes = (now_ts - parsed.timestamp()) / 60.0
                else:
                    drift_minutes = (now_ts - last.timestamp()) / 60.0
            except Exception:
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
            last_str = last.isoformat()[:19]
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
