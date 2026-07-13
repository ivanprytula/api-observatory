"""MCP tool definitions exposing the observatory's toolset to LLM clients.

Each tool is a thin wrapper over `services.mcp.ingestor_client` — the real
authenticated HTTP calls live there, this module only defines the LLM-facing
surface (names, docstrings, argument shapes). Docstrings here are what an MCP
client actually sees as the tool description, so they're written as real
usage guidance, not restated function names.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from services.mcp import ingestor_client


mcp = FastMCP("api-observatory")


@mcp.tool()
async def list_sources(
    is_active: bool | None = None, offset: int = 0, limit: int = 20
) -> Any:
    """List registered API source profiles being monitored.

    Use `is_active=True` to see only sources currently being probed.
    """
    return await ingestor_client.list_sources(
        is_active=is_active, offset=offset, limit=limit
    )


@mcp.tool()
async def get_source(source_id: int) -> Any:
    """Get one source profile's registration details by its ID."""
    return await ingestor_client.get_source(source_id)


@mcp.tool()
async def get_source_summary() -> Any:
    """Get aggregate statistics across all registered sources (counts, type
    breakdown, cost estimates) — a good first call for a bird's-eye view."""
    return await ingestor_client.get_source_summary()


@mcp.tool()
async def probe_source_health(source_id: int) -> Any:
    """Run a live reachability/latency probe against one source right now.

    Makes a real outbound HTTP request to the source's base URL — use for an
    on-demand check, not for routine polling (the platform already probes
    sources on a schedule; see scorecards for historical uptime instead).
    """
    return await ingestor_client.probe_source_health(source_id)


@mcp.tool()
async def list_scorecards(
    days: int | None = None,
    source_id: int | None = None,
    limit: int | None = None,
) -> Any:
    """List reliability scorecards (uptime %, p95 latency, error-budget burn
    rate) for active sources over a look-back window (default 7 days)."""
    return await ingestor_client.list_scorecards(
        days=days, source_id=source_id, limit=limit
    )


@mcp.tool()
async def get_scorecard(source_id: int, days: int | None = None) -> Any:
    """Get the reliability scorecard for one specific source."""
    return await ingestor_client.get_scorecard(source_id, days=days)


@mcp.tool()
async def list_contract_snapshots(
    source_id: int, offset: int = 0, limit: int = 20
) -> Any:
    """List the schema contract snapshots recorded for one source, most
    recent first — the history that contract drift is detected against."""
    return await ingestor_client.list_contract_snapshots(
        source_id, offset=offset, limit=limit
    )


@mcp.tool()
async def list_drift_events(source_id: int, offset: int = 0, limit: int = 20) -> Any:
    """List detected API contract drift events for one source (additive,
    breaking, etc.), most recent first."""
    return await ingestor_client.list_drift_events(
        source_id, offset=offset, limit=limit
    )


@mcp.tool()
async def get_compatibility_report(source_id: int) -> Any:
    """Get a source's overall compatibility score and its latest drift
    breakdown — a quick health signal without listing every event."""
    return await ingestor_client.get_compatibility_report(source_id)


@mcp.tool()
async def get_agent_run(run_id: int) -> Any:
    """Get the current status of one incident-triage agent run, including its
    root-cause hypothesis, severity assessment, and recommended action once
    the agent has finished analyzing it. Status is one of: pending, running,
    awaiting_review, approved, rejected, failed."""
    return await ingestor_client.get_agent_run(run_id)


@mcp.tool()
async def resume_agent_run(run_id: int, approve: bool) -> Any:
    """Approve or reject a paused agent run (must be in `awaiting_review`
    status) — the human-in-the-loop step before its recommended action is
    acted on. Set `approve=True` to accept the agent's analysis and let it
    proceed, or `approve=False` to reject it."""
    return await ingestor_client.resume_agent_run(run_id, approve=approve)
