"""Panel 2: Probe Scheduler controls and status.

Split into:
  - ``use_*`` — data-fetching hooks
  - ``render_*`` — pure display from pre-fetched data
"""

from __future__ import annotations

from services.dashboard.core.api_client import (
    DashboardApiError,
    api,
    fetch_prometheus_metrics,
    fetch_scheduler_jobs,
)
from services.dashboard.core.auth import AuthManager
from services.dashboard.core.metrics_parser import (
    parse_metric_value,
    parse_prometheus_counter,
)
from services.dashboard.ui.protocols import UIAdapter


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


def use_sources(token: str = "") -> dict:
    try:
        sources = api.sources.list(token=token)
    except DashboardApiError:
        sources = []
    return {"sources": sources}


def use_queue_retry_metrics() -> dict:
    try:
        metrics = fetch_prometheus_metrics()
    except DashboardApiError:
        metrics = ""
    return {
        "dlq_depth": parse_metric_value(metrics, "dead_letter_queue_depth") or 0,
        "retries_total": parse_prometheus_counter(metrics, "retry_total"),
        "failed_total": parse_prometheus_counter(metrics, "jobs_failed_total"),
    }


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def render_probe_scheduler(ui: UIAdapter, auth: AuthManager) -> None:
    """Render the probe scheduler panel with manual probe controls."""
    ui.header("Probe Scheduler")

    if not auth.state.logged_in:
        ui.show_warning("Log in to run probes.")
        return

    data = use_sources(token=auth.access_token)
    sources = data["sources"]
    if not sources:
        ui.show_info("No sources registered yet — run `just seed-probes` first.")
        return

    probe_results = ui.probe_results

    col_all, col_clear = ui.columns([1, 5])
    if col_all.button("▶ Probe all", key="probe_all"):
        for src in sources:
            try:
                result = api.sources.probe(src.id, token=auth.access_token)
                probe_results[src.id] = result.model_dump()
            except Exception as exc:
                probe_results[src.id] = {"error": str(exc)}
        ui.probe_results = probe_results
        ui.rerun()

    if col_clear.button("🗑 Clear results", key="probe_clear"):
        ui.probe_results = {}
        ui.rerun()

    for src in sources:
        sid = src.id
        col_name, col_btn, col_result = ui.columns([2, 1, 4])
        col_name.markdown(f"**{src.name}** `#{sid}`")

        if col_btn.button("▶ Probe", key=f"probe_{sid}"):
            try:
                result = api.sources.probe(sid, token=auth.access_token)
                probe_results[sid] = result.model_dump()
            except Exception as exc:
                probe_results[sid] = {"error": str(exc)}
            ui.probe_results = probe_results
            ui.rerun()

        result = probe_results.get(sid)
        if result:
            if "error" in result and result["error"]:
                col_result.error(result["error"])
            else:
                ok = result.get("reachable", False)
                latency = result.get("latency_ms")
                sla = result.get("sla_breach", False)
                status_icon = "✅" if ok else "❌"
                latency_str = f"{latency:.0f} ms" if latency is not None else "—"
                sla_str = " 🔥 SLA breach" if sla else ""
                col_result.markdown(
                    f"{status_icon} reachable={ok} &nbsp; ⏱ {latency_str}{sla_str}"
                )

    with ui.expander("Scheduler job status", expanded=False):
        try:
            jobs = fetch_scheduler_jobs()
            running = jobs.get("scheduler_running", False)
            running_icon = "✅" if running else "❌"
            ui.caption(
                f"Scheduler running:{running_icon} | Jobs: {jobs.get('job_count', 0)}"
            )
            for jname, jinfo in jobs.get("jobs", {}).items():
                c1, c2, c3 = ui.columns(3)
                c1.markdown(f"`{jname}`")
                c2.caption(
                    f"runs: {jinfo.get('total_executions', 0)} "
                    f"errors:{jinfo.get('error_count', 0)}"
                )
                next_run = jinfo.get("next_run_time", "—")
                next_str = str(next_run)[:19] if next_run else "—"
                c3.caption(f"next: {next_str}")
        except DashboardApiError as exc:
            ui.show_warning(f"Could not fetch scheduler status: {exc}")


def render_queue_retry_health(ui: UIAdapter, auth: AuthManager) -> None:
    """Render Queue & Retry Health metrics."""
    ui.header("📦 Queue & Retry Health")

    data = use_queue_retry_metrics()
    dlq_depth = data["dlq_depth"]
    retries_total = data["retries_total"]
    failed_total = data["failed_total"]

    q1, q2, q3 = ui.columns(3)
    q1.metric("Dead-letter queue depth", f"{dlq_depth:,.0f}")
    q2.metric("Retries (total)", f"{retries_total:,.0f}")
    q3.metric("Failed jobs (total)", f"{failed_total:,.0f}")

    if dlq_depth > 0:
        ui.show_warning(
            f"DLQ has {dlq_depth:,.0f} messages — review with the ops runbook."
        )
    else:
        ui.show_success("Dead-letter queue is empty.")
