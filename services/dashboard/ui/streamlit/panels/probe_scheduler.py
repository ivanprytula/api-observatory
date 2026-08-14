"""Panel 2: Probe Scheduler controls and status.

Split into:
  - ``use_*`` — data-fetching hooks
  - ``render_*`` — pure display from pre-fetched data
"""

from __future__ import annotations

import httpx

from services.dashboard.core.api_client import (
    API_REQUEST_ERRORS,
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


_PROBE_ERROR_MAP = {
    "Connection refused": "Target actively refused the connection.",
    "Timeout": "Probe timed out — target may be overloaded or unreachable.",
    "DNS resolution failed": "Could not resolve the hostname.",
    "Name or service not known": "Could not resolve the hostname.",
    "No route to host": "Network is unreachable.",
}


def _friendly_probe_error(exc: Exception) -> str:
    msg = str(exc)
    for needle, friendly in _PROBE_ERROR_MAP.items():
        if needle.lower() in msg.lower():
            return friendly
    if isinstance(exc, httpx.TimeoutException):
        return "Probe timed out — target may be overloaded or unreachable."
    if isinstance(exc, httpx.ConnectError):
        return "Could not connect to the target."
    return msg


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


def use_sources(token: str = "") -> dict:
    try:
        sources = api.sources.list(token=token)
    except API_REQUEST_ERRORS:
        sources = []
    return {"sources": sources}


def use_queue_retry_metrics() -> dict:
    try:
        metrics = fetch_prometheus_metrics()
    except API_REQUEST_ERRORS:
        metrics = ""
    return {
        "queue_depth": parse_metric_value(metrics, "pipeline_background_jobs_in_queue") or 0,
        "retries_total": parse_prometheus_counter(
            metrics, "pipeline_job_executions_total", labels={"status": "failed"}
        ),
        "failed_total": parse_prometheus_counter(
            metrics, "pipeline_background_jobs_processed_total", labels={"status": "failed"}
        ),
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
        return

    probe_results = ui.probe_results

    col_all, col_clear = ui.columns([1, 5])
    if col_all.button("Probe all", key="probe_all"):
        total = len(sources)
        status_holder = ui.empty()
        for idx, src in enumerate(sources, start=1):
            status_holder.info(f"Probing {src.name} ({idx}/{total})...")
            try:
                result = api.sources.probe(src.id, token=auth.access_token)
                probe_results[src.id] = result.model_dump()
            except Exception as exc:
                probe_results[src.id] = {"error": _friendly_probe_error(exc)}
        ui.probe_results = probe_results
        status_holder.empty()
        ui.rerun()

    if col_clear.button("🗑 Clear results", key="probe_clear"):
        ui.probe_results = {}
        ui.rerun()

    for src in sources:
        sid = src.id
        col_name, col_btn, col_result = ui.columns([2, 1, 4])
        col_name.markdown(f"**{src.name}** `#{sid}`")

        if col_btn.button("Probe", key=f"probe_{sid}"):
            try:
                result = api.sources.probe(sid, token=auth.access_token)
                probe_results[sid] = result.model_dump()
            except Exception as exc:
                probe_results[sid] = {"error": _friendly_probe_error(exc)}
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
            jobs = fetch_scheduler_jobs(auth=auth)
            running = jobs.get("scheduler_running", False)
            running_icon = "✅" if running else "❌"
            ui.caption(
                f"Scheduler running:{running_icon} | Jobs: {jobs.get('job_count', 0)}"
            )
            for jname, jinfo in jobs.get("jobs", {}).items():
                c1, c2, c3 = ui.columns(3)
                c1.markdown(f"`{jname}`")
                success_count = jinfo.get("success_count", 0)
                failure_count = jinfo.get("failure_count", 0)
                c2.caption(
                    f"runs: {success_count + failure_count} errors:{failure_count}"
                )
                next_run = jinfo.get("next_run_time", "—")
                next_str = str(next_run)[:19] if next_run else "—"
                c3.caption(f"next: {next_str}")
        except API_REQUEST_ERRORS as exc:
            ui.show_warning(f"Could not fetch scheduler status: {exc}")


def render_queue_retry_health(ui: UIAdapter, auth: AuthManager) -> None:
    """Render Queue & Retry Health metrics."""
    ui.header("📦 Queue & Retry Health")

    data = use_queue_retry_metrics()
    queue_depth = data["queue_depth"]
    retries_total = data["retries_total"]
    failed_total = data["failed_total"]

    q1, q2, q3 = ui.columns(3)
    q1.metric("Queue depth", f"{queue_depth:,.0f}")
    q2.metric("Job failures (total)", f"{retries_total:,.0f}")
    q3.metric("Background failures (total)", f"{failed_total:,.0f}")

    if queue_depth > 0:
        ui.show_warning(
            f"Queue has {queue_depth:,.0f} pending jobs — review worker health."
        )
    else:
        ui.show_success("Queue is empty.")
