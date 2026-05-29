"""Pydantic schemas for BI and Reporting endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MetricPoint(BaseModel):
    """Single timestamped point in a KPI series."""

    timestamp: datetime = Field(..., description="UTC timestamp for the KPI sample.")
    value: float = Field(..., description="Numeric KPI value at the given timestamp.")


class MetricSeries(BaseModel):
    """Rollup of KPI values for one source and metric."""

    series_id: str = Field(..., description="Stable identifier for this metric series.")
    source_id: int = Field(..., description="Source profile ID this series belongs to.")
    source_name: str = Field(..., description="Human-friendly source name.")
    metric: str = Field(
        ..., description="KPI metric key, for example compatibility_score."
    )
    unit: str = Field(
        ..., description="Unit for metric values, for example score or percent."
    )
    points: list[MetricPoint] = Field(
        ...,
        description="Ordered KPI samples in the selected window.",
    )
    summary: str = Field(..., description="Short interpretation of this KPI rollup.")


class CohortReport(BaseModel):
    """Comparison row for one operational cohort."""

    cohort_id: str = Field(..., description="Stable identifier for the cohort row.")
    cohort_name: str = Field(..., description="Label used in dashboards and exports.")
    source_id: int = Field(
        ..., description="Source profile represented by this cohort row."
    )
    sample_size: int = Field(
        ...,
        ge=0,
        description="Number of events included in the cohort window.",
    )
    avg_compatibility_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Average compatibility score across cohort events.",
    )
    breaking_rate_pct: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Percent of events classified as breaking changes.",
    )
    avg_sla_gap_ms: float = Field(
        ..., description="Approximate SLA gap in milliseconds."
    )
    rank: int = Field(..., ge=1, description="Relative rank among returned cohorts.")


class DashboardPreset(BaseModel):
    """Reusable dashboard configuration for BI consumers."""

    preset_id: str = Field(..., description="Stable preset identifier.")
    name: str = Field(..., description="Display name for this dashboard preset.")
    description: str = Field(..., description="Purpose and audience for this preset.")
    widgets: list[str] = Field(
        ..., description="Ordered widget identifiers included in preset."
    )


class ExportJobRequest(BaseModel):
    """Request body for creating a BI export job."""

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "preset_id": "ops-scorecard",
                    "export_format": "json",
                    "source_ids": [1, 2],
                }
            ]
        }
    }

    preset_id: str = Field(..., description="Dashboard preset to export.")
    export_format: str = Field(..., description="Export format, currently json or csv.")
    source_ids: list[int] | None = Field(
        default=None,
        description="Optional source filters to constrain export payload.",
    )


class ExportJob(BaseModel):
    """Represents an asynchronous BI export operation."""

    export_id: str = Field(..., description="Export job identifier.")
    status: str = Field(..., description="Current job status, for example completed.")
    preset_id: str = Field(..., description="Preset used to build the export.")
    export_format: str = Field(..., description="Requested export format.")
    created_at: datetime = Field(..., description="UTC timestamp when job was created.")
    detail: str = Field(
        ..., description="Operational detail for audit and user feedback."
    )


class MetricSeriesListResponse(BaseModel):
    """Response payload for KPI rollups."""

    items: list[MetricSeries] = Field(..., description="Metric series items.")
    total: int = Field(..., ge=0, description="Total number of returned series.")


class CohortReportListResponse(BaseModel):
    """Response payload for cohort comparison."""

    items: list[CohortReport] = Field(..., description="Cohort comparison rows.")
    total: int = Field(..., ge=0, description="Total number of returned cohorts.")


class DashboardPresetListResponse(BaseModel):
    """Response payload for dashboard presets."""

    items: list[DashboardPreset] = Field(..., description="Dashboard preset items.")
    total: int = Field(..., ge=0, description="Total number of returned presets.")


class CostValueRow(BaseModel):
    """Cost-to-value breakdown for a single source.

    Dimensions:
    - ``cost_per_observation_usd``: average cost to produce one successful ingestion observation.
    - ``cost_per_insight_usd``: average cost to produce one actionable drift insight.
    Both are ``None`` when the denominator is zero (no observations or no insights yet).
    """

    source_id: int = Field(..., description="Source profile ID.")
    source_name: str = Field(..., description="Human-friendly source label.")
    owner_team: str | None = Field(
        None, description="Team responsible for this source, if set."
    )
    cost_per_call_usd: float = Field(
        ...,
        ge=0.0,
        description="Configured unit cost per API call in USD (0 if not set).",
    )
    total_calls: int = Field(
        ..., ge=0, description="Number of ingestion calls (snapshots) in the window."
    )
    total_cost_usd: float = Field(
        ..., ge=0.0, description="Total spend in USD across the window."
    )
    successful_observations: int = Field(
        ...,
        ge=0,
        description=(
            "Ingestion calls that did NOT result in a breaking drift event. "
            "These are the calls that produced clean, usable observations."
        ),
    )
    insights_generated: int = Field(
        ...,
        ge=0,
        description="Drift events produced in the window (each = one actionable insight).",
    )
    cost_per_observation_usd: float | None = Field(
        None,
        description=(
            "total_cost_usd / successful_observations. "
            "Null when successful_observations is 0."
        ),
    )
    cost_per_insight_usd: float | None = Field(
        None,
        description="total_cost_usd / insights_generated. Null when insights_generated is 0.",
    )


class TeamCostSummary(BaseModel):
    """Cost rollup for all sources belonging to one team."""

    team: str = Field(
        ...,
        description='Team name, or "unassigned" for sources without an owner_team.',
    )
    total_cost_usd: float = Field(
        ..., ge=0.0, description="Total spend across all team sources in the window."
    )
    total_calls: int = Field(
        ..., ge=0, description="Total ingestion calls across all team sources."
    )
    total_insights: int = Field(
        ..., ge=0, description="Total drift insights across all team sources."
    )
    cost_per_insight_usd: float | None = Field(
        None,
        description="total_cost_usd / total_insights. Null when total_insights is 0.",
    )


class CostValueResponse(BaseModel):
    """Cost-to-value chart data across sources and teams.

    Contains per-source rows for detailed drill-down and team-level summaries
    for executive reporting.  ``total_cost_usd`` is the grand total across all
    returned rows.
    """

    rows: list[CostValueRow] = Field(
        ...,
        description="Per-source cost-to-value breakdown, ordered by total_cost_usd descending.",
    )
    team_summaries: list[TeamCostSummary] = Field(
        ...,
        description="Cost rollup per team, ordered by total_cost_usd descending.",
    )
    total_cost_usd: float = Field(
        ..., ge=0.0, description="Grand total spend across all returned sources."
    )
    window_days: int = Field(
        ..., ge=1, description="Look-back window in days used for this report."
    )


class DriftHeatmapCell(BaseModel):
    """Single cell in the schema drift heatmap grid.

    Each cell represents one (source, severity) intersection and carries
    an event count and a heat_value normalized to [0.0, 1.0] across the
    whole heatmap so consumers can drive a colour scale directly.
    """

    source_id: int = Field(..., description="Source profile ID.")
    source_name: str = Field(..., description="Human-friendly source label.")
    severity: str = Field(
        ...,
        description="Drift severity bucket: none | low | medium | high | critical.",
    )
    count: int = Field(
        ..., ge=0, description="Number of drift events in the selected window."
    )
    heat_value: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Relative intensity in [0.0, 1.0] normalised across all cells. "
            "Use this directly as an opacity or colour-scale input."
        ),
    )


class DriftHeatmapResponse(BaseModel):
    """Schema drift heatmap across sources and severity levels.

    The heatmap is a sparse grid: only cells with at least one event are
    included.  ``sources`` and ``severities`` list all labels present in
    the response so the caller can build the full grid without scanning
    every cell.
    """

    sources: list[str] = Field(
        ..., description="Ordered source name labels present in the heatmap."
    )
    severities: list[str] = Field(
        ...,
        description=(
            "Severity levels present in the heatmap, ordered from highest to lowest: "
            "critical, high, medium, low, none."
        ),
    )
    cells: list[DriftHeatmapCell] = Field(
        ..., description="Sparse set of (source, severity) cells with event counts."
    )
    total_events: int = Field(
        ..., ge=0, description="Total drift events included across all cells."
    )
    window_days: int = Field(
        ..., ge=1, description="Look-back window in days used for this heatmap."
    )


class FreshnessSourceRow(BaseModel):
    """Freshness SLA status for one source.

    ``status`` is one of:
    - ``ok``: last snapshot is within the SLA threshold.
    - ``warning``: last snapshot age is between 75 % and 100 % of the threshold.
    - ``breached``: last snapshot age exceeds the threshold.
    - ``no_data``: no snapshots observationed in the window.
    """

    source_id: int = Field(..., description="Source profile ID.")
    source_name: str = Field(..., description="Human-friendly source label.")
    owner_team: str | None = Field(
        None, description="Team responsible for this source."
    )
    last_snapshot_at: datetime | None = Field(
        None, description="UTC timestamp of the most recent ingestion snapshot."
    )
    age_seconds: int | None = Field(
        None,
        ge=0,
        description="Seconds elapsed since the last snapshot.  None when no data.",
    )
    sla_threshold_seconds: int = Field(
        ..., ge=1, description="SLA threshold in seconds configured for this report."
    )
    status: str = Field(
        ..., description="Freshness status: ok | warning | breached | no_data."
    )
    total_snapshots: int = Field(
        ..., ge=0, description="Total snapshots ingested in the look-back window."
    )
    incident_count: int = Field(
        ..., ge=0, description="Number of SLA gap incidents detected in the window."
    )


class FreshnessIncident(BaseModel):
    """A single gap between consecutive snapshots that exceeded the SLA threshold.

    ``is_open`` is ``True`` when no follow-up snapshot has closed the gap yet,
    meaning the source is currently breaching its SLA.
    """

    source_id: int = Field(..., description="Source profile ID.")
    source_name: str = Field(..., description="Human-friendly source label.")
    gap_start: datetime = Field(
        ..., description="UTC timestamp when the gap began (last snapshot before gap)."
    )
    gap_end: datetime | None = Field(
        None,
        description=(
            "UTC timestamp when the gap closed (next snapshot after gap). "
            "None if the incident is still open."
        ),
    )
    gap_seconds: int = Field(..., ge=0, description="Duration of the gap in seconds.")
    is_open: bool = Field(
        ...,
        description="True when no follow-up snapshot has been received yet.",
    )


class FreshnessSLAResponse(BaseModel):
    """Freshness SLA dashboard across sources with incident timeline.

    ``sources`` lists the freshness status for every matched source.
    ``incidents`` is the chronological incident timeline (newest first) of
    SLA gaps that exceeded the configured threshold.
    """

    sources: list[FreshnessSourceRow] = Field(
        ..., description="Per-source freshness SLA status rows."
    )
    incidents: list[FreshnessIncident] = Field(
        ...,
        description=(
            "Chronological incident list (newest first) of SLA gaps that exceeded "
            "the configured threshold."
        ),
    )
    total_breached: int = Field(
        ..., ge=0, description="Number of sources currently breaching the SLA."
    )
    total_ok: int = Field(
        ..., ge=0, description="Number of sources within the SLA threshold."
    )
    total_no_data: int = Field(
        ..., ge=0, description="Number of sources with no data in the window."
    )
    window_days: int = Field(
        ..., ge=1, description="Look-back window in days used for this report."
    )
    sla_threshold_hours: int = Field(
        ..., ge=1, description="Freshness SLA threshold in hours used for this report."
    )


# ---------------------------------------------------------------------------
# Executive summary schemas
# ---------------------------------------------------------------------------


class ActionItem(BaseModel):
    """A single recommended action in the executive action list."""

    priority: str = Field(
        ...,
        description="Action urgency: critical | high | medium | low.",
    )
    category: str = Field(
        ...,
        description="Action domain: drift | freshness | cost | reliability.",
    )
    title: str = Field(..., description="Short action title for dashboard display.")
    description: str = Field(
        ...,
        description="Actionable detail explaining what to do and why.",
    )
    source_id: int | None = Field(
        None,
        description="Source profile ID if the action is source-specific.",
    )
    source_name: str | None = Field(
        None,
        description="Source name if the action is source-specific.",
    )


class DriftSummarySection(BaseModel):
    """Drift health rollup for the executive summary."""

    total_sources_with_drift: int = Field(
        ...,
        ge=0,
        description="Sources that had at least one drift event in the window.",
    )
    total_events: int = Field(
        ..., ge=0, description="Total drift events in the window."
    )
    avg_compatibility_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Average compatibility score across all sources with drift events.",
    )
    breaking_source_count: int = Field(
        ...,
        ge=0,
        description="Number of sources with at least one breaking drift event.",
    )


class FreshnessSummarySection(BaseModel):
    """Freshness SLA rollup for the executive summary."""

    total_sources: int = Field(
        ..., ge=0, description="Total sources evaluated for freshness."
    )
    breached: int = Field(
        ..., ge=0, description="Sources currently breaching the SLA threshold."
    )
    warning: int = Field(
        ..., ge=0, description="Sources approaching the SLA threshold (75–100 %)."
    )
    ok: int = Field(..., ge=0, description="Sources within the SLA threshold.")
    no_data: int = Field(..., ge=0, description="Sources with no data in the window.")
    open_incidents: int = Field(
        ..., ge=0, description="Number of currently open SLA gap incidents."
    )


class CostSummarySection(BaseModel):
    """Cost efficiency rollup for the executive summary."""

    total_cost_usd: float = Field(
        ..., ge=0.0, description="Total spend across all sources in the window."
    )
    total_sources: int = Field(
        ..., ge=0, description="Total sources with cost or snapshot data."
    )
    avg_cost_per_insight_usd: float | None = Field(
        None,
        description=(
            "Average cost per drift insight across sources with non-zero spend. "
            "Null when no spend is observationed."
        ),
    )
    highest_cost_source_name: str | None = Field(
        None,
        description="Name of the highest-spend source. Null when no cost data exists.",
    )


class ExecutiveSummaryResponse(BaseModel):
    """Weekly executive summary aggregating drift, freshness, and cost signals.

    Synthesises KPI rollups, freshness SLA status, and cost-to-value data
    into a single leadership dashboard view.  The ``action_items`` list is
    sorted by priority (critical first) and capped at ``max_actions``.
    """

    generated_at: datetime = Field(
        ..., description="UTC timestamp when this summary was generated."
    )
    window_days: int = Field(..., ge=1, description="Look-back window in days.")
    drift: DriftSummarySection = Field(..., description="Drift health rollup.")
    freshness: FreshnessSummarySection = Field(..., description="Freshness SLA rollup.")
    cost: CostSummarySection = Field(..., description="Cost efficiency rollup.")
    action_items: list[ActionItem] = Field(
        ...,
        description="Prioritised recommended actions ordered critical → low.",
    )
    total_actions: int = Field(
        ..., ge=0, description="Total number of action items returned."
    )
