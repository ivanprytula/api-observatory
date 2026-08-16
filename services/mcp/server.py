"""MCP tool definitions exposing the observatory's toolset to LLM clients.

Each tool is a thin wrapper over `services.mcp.ingestor_client` — the real
authenticated HTTP calls live there, this module only defines the LLM-facing
surface (names, docstrings, argument shapes, return schemas). Docstrings here
are what an MCP client actually sees as the tool description, so they're written
as real usage guidance, not restated function names.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from libs.contracts.schemas_dashboard import (
    CompatibilityReportResponse,
    ContractSnapshotListResponse,
    DriftEventListResponse,
    ProviderScorecard,
    ScorecardListResponse,
    SourceHealthResponse,
    SourceProfileListResponse,
    SourceProfileResponse,
)
from services.mcp import ingestor_client


mcp = FastMCP("api-observatory")


@mcp.tool()
async def list_sources(
    is_active: bool | None = None, offset: int = 0, limit: int = 20
) -> SourceProfileListResponse:
    """List registered API source profiles being monitored.

    Returns a paginated list with `items`, `total`, `offset`, and `limit`.
    Use `is_active=True` to see only sources currently being probed.
    """
    return await ingestor_client.list_sources(
        is_active=is_active, offset=offset, limit=limit
    )


@mcp.tool()
async def get_source(source_id: int) -> SourceProfileResponse:
    """Get one source profile's registration details by its ID.

    Returns `id`, `name`, `base_url`, `health_check_path`, `probe_interval_seconds`,
    `is_active`, `tenant_id`, `latency_threshold_ms`, `incident_failure_threshold`,
    `incident_cooldown_seconds`, `created_at`, and `updated_at`.
    """
    return await ingestor_client.get_source(source_id)


@mcp.tool()
async def get_source_summary() -> dict[str, Any]:
    """Get aggregate statistics across all registered sources.

    Returns `total_sources` (int), `active_sources` (int), `inactive_sources` (int),
    and `avg_probe_interval_seconds` (float | None).
    """
    return await ingestor_client.get_source_summary()


@mcp.tool()
async def probe_source_health(source_id: int) -> SourceHealthResponse:
    """Run a live reachability/latency probe against one source right now.

    Returns `source_id`, `target_url`, `reachable`, `status_code`, `latency_ms`,
    `sla_breach`, `error`, and `checked_at`. Makes a real outbound HTTP request
    to the source's base URL — use for an on-demand check, not for routine
    polling (the platform already probes sources on a schedule; see scorecards
    for historical uptime instead).
    """
    return await ingestor_client.probe_source_health(source_id)


@mcp.tool()
async def list_scorecards(
    days: int | None = None,
    source_id: int | None = None,
    limit: int | None = None,
) -> ScorecardListResponse:
    """List reliability scorecards for active sources over a look-back window.

    Returns a list of `ProviderScorecard` items and `total`. Each scorecard
    includes `source_id`, `source_name`, `window_days`, `sample_count`,
    `error_count`, `uptime_pct`, `avg_latency_ms`, `p50_latency_ms`,
    `p95_latency_ms`, `slo_target_pct`, `error_budget_burn_rate`, and
    `generated_at`. Default look-back is 7 days.
    """
    return await ingestor_client.list_scorecards(
        days=days, source_id=source_id, limit=limit
    )


@mcp.tool()
async def get_scorecard(source_id: int, days: int | None = None) -> ProviderScorecard:
    """Get the reliability scorecard for one specific source.

    Returns `source_id`, `source_name`, `window_days`, `sample_count`,
    `error_count`, `uptime_pct`, `avg_latency_ms`, `p50_latency_ms`,
    `p95_latency_ms`, `slo_target_pct`, `error_budget_burn_rate`, and
    `generated_at`.
    """
    return await ingestor_client.get_scorecard(source_id, days=days)


@mcp.tool()
async def list_contract_snapshots(
    source_id: int, offset: int = 0, limit: int = 20
) -> ContractSnapshotListResponse:
    """List the schema contract snapshots recorded for one source, most
    recent first — the history that contract drift is detected against.

    Returns `items` (each with `id`, `source_id`, `schema_version`,
    `payload_schema`, `schema_fingerprint`, `compatibility_score`,
    `snapshot_note`, `created_at`, `updated_at`), `total`, `offset`, and `limit`.
    """
    return await ingestor_client.list_contract_snapshots(
        source_id, offset=offset, limit=limit
    )


@mcp.tool()
async def list_drift_events(
    source_id: int, offset: int = 0, limit: int = 20
) -> DriftEventListResponse:
    """List detected API contract drift events for one source (additive,
    breaking, etc.), most recent first.

    Returns `items` (each with `id`, `source_id`, `previous_snapshot_id`,
    `current_snapshot_id`, `event_type`, `severity`, `added_fields`,
    `removed_fields`, `type_changed_fields`, `compatibility_score`,
    `summary`, `created_at`), `total`, `offset`, and `limit`.
    """
    return await ingestor_client.list_drift_events(
        source_id, offset=offset, limit=limit
    )


@mcp.tool()
async def get_compatibility_report(source_id: int) -> CompatibilityReportResponse:
    """Get a source's overall compatibility score and its latest drift
    breakdown — a quick health signal without listing every event.

    Returns `source_id`, `latest_snapshot_id`, `previous_snapshot_id`,
    `compatibility_score`, `drift_detected`, `event_type`, `severity`,
    `added_fields`, `removed_fields`, and `type_changed_fields`.
    """
    return await ingestor_client.get_compatibility_report(source_id)


@mcp.tool()
async def get_agent_run(run_id: int) -> dict[str, Any]:
    """Get the current status of one incident-triage agent run, including its
    root-cause hypothesis, severity assessment, and recommended action once
    the agent has finished analyzing it.

    Returns `id` (int), `observation_id` (int), `status` (str: pending, running,
    awaiting_review, approved, rejected, failed), `root_cause_hypothesis` (str | None),
    `severity_assessment` (str | None), `recommended_action` (str | None),
    `confidence_score` (float | None), `reviewer_user_id` (int | None),
    `reviewed_at` (datetime | None), `created_at` (datetime), `updated_at` (datetime | None).
    """
    return await ingestor_client.get_agent_run(run_id)


@mcp.tool()
async def resume_agent_run(run_id: int, approve: bool) -> dict[str, Any]:
    """Approve or reject a paused agent run (must be in `awaiting_review`
    status) — the human-in-the-loop step before its recommended action is
    acted on. Set `approve=True` to accept the agent's analysis and let it
    proceed, or `approve=False` to reject it.

    Returns the updated run object with the new `status` (`approved` or `rejected`)
    and `reviewer_user_id` derived server-side from the caller's JWT.
    """
    return await ingestor_client.resume_agent_run(run_id, approve=approve)
