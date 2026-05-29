"""BI and reporting endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.reporting import (
    CohortReportListResponse,
    CostValueResponse,
    DashboardPresetListResponse,
    DriftHeatmapResponse,
    ExecutiveSummaryResponse,
    ExportJob,
    ExportJobRequest,
    FreshnessSLAResponse,
    MetricSeriesListResponse,
)
from services.ingestor.constants import (
    API_V1_PREFIX,
    MAX_PAGE_SIZE,
    REPORTING_DEFAULT_COHORT_LIMIT,
    REPORTING_DEFAULT_COST_LIMIT,
    REPORTING_DEFAULT_DAYS,
    REPORTING_DEFAULT_FRESHNESS_LIMIT,
    REPORTING_DEFAULT_HEATMAP_LIMIT,
    REPORTING_DEFAULT_SLA_THRESHOLD_HOURS,
    REPORTING_EXEC_SUMMARY_DEFAULT_SOURCE_LIMIT,
    REPORTING_EXEC_SUMMARY_MAX_ACTIONS,
    REPORTING_MAX_DAYS,
    REPORTING_MAX_SLA_THRESHOLD_HOURS,
)
from services.ingestor.database import get_db
from services.ingestor.repositories.reporting import (
    create_export_job,
    get_cost_value_chart,
    get_drift_heatmap,
    get_executive_summary,
    get_freshness_sla,
    list_cohort_reports,
    list_dashboard_presets,
    list_metric_series,
)


router = APIRouter(prefix=f"{API_V1_PREFIX}/reporting", tags=["reporting"])

type DbDep = Annotated[AsyncSession, Depends(get_db)]

_R422 = {
    "422": {
        "description": "Validation error in query parameters or request payload.",
    }
}


@router.get(
    "/kpi-rollups",
    response_model=MetricSeriesListResponse,
    summary="Get KPI rollups",
    responses={**_R422},
)
async def get_kpi_rollups(
    db: DbDep,
    days: Annotated[
        int,
        Query(ge=1, le=REPORTING_MAX_DAYS, description="Time window in days."),
    ] = REPORTING_DEFAULT_DAYS,
    source_id: Annotated[
        int | None, Query(ge=1, description="Optional source filter.")
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_PAGE_SIZE,
            description="Maximum number of source series to return.",
        ),
    ] = REPORTING_DEFAULT_COHORT_LIMIT,
) -> MetricSeriesListResponse:
    """Return KPI metric rollups derived from recent drift signals."""
    items = await list_metric_series(db, days=days, source_id=source_id, limit=limit)
    return MetricSeriesListResponse(items=items, total=len(items))


@router.get(
    "/cohort-comparison",
    response_model=CohortReportListResponse,
    summary="Compare source cohorts",
    responses={**_R422},
)
async def get_cohort_comparison(
    db: DbDep,
    days: Annotated[
        int,
        Query(ge=1, le=REPORTING_MAX_DAYS, description="Time window in days."),
    ] = REPORTING_DEFAULT_DAYS,
    limit: Annotated[
        int,
        Query(
            ge=1, le=MAX_PAGE_SIZE, description="Maximum number of cohorts to return."
        ),
    ] = REPORTING_DEFAULT_COHORT_LIMIT,
) -> CohortReportListResponse:
    """Return ranked cohort comparison rows for reliability analysis."""
    items = await list_cohort_reports(db, days=days, limit=limit)
    return CohortReportListResponse(items=items, total=len(items))


@router.get(
    "/dashboard-presets",
    response_model=DashboardPresetListResponse,
    summary="List dashboard presets",
)
async def get_dashboard_presets() -> DashboardPresetListResponse:
    """Return built-in dashboard presets for BI consumers."""
    items = list_dashboard_presets()
    return DashboardPresetListResponse(items=items, total=len(items))


@router.post(
    "/exports",
    response_model=ExportJob,
    status_code=status.HTTP_201_CREATED,
    summary="Create export job",
    responses={**_R422},
)
async def create_reporting_export(
    payload: ExportJobRequest,
) -> ExportJob:
    """Create an export job from selected BI dashboard preset."""
    return create_export_job(payload)


@router.get(
    "/drift-heatmap",
    response_model=DriftHeatmapResponse,
    summary="Get schema drift heatmap",
    responses={**_R422},
)
async def get_reporting_drift_heatmap(
    db: DbDep,
    days: Annotated[
        int,
        Query(ge=1, le=REPORTING_MAX_DAYS, description="Look-back window in days."),
    ] = REPORTING_DEFAULT_DAYS,
    source_ids: Annotated[
        list[int] | None,
        Query(description="Optional list of source IDs to include."),
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_PAGE_SIZE,
            description="Maximum number of sources to include in the heatmap.",
        ),
    ] = REPORTING_DEFAULT_HEATMAP_LIMIT,
) -> DriftHeatmapResponse:
    """Return a schema drift heatmap grouped by source and severity.

    Each cell in the heatmap represents the drift event count for one
    (source, severity) combination inside the selected time window.
    The ``heat_value`` field is normalised to [0.0, 1.0] across all cells
    so it can be used directly as an opacity or colour-scale input for BI
    dashboards.  Only cells with at least one event are included; the
    ``sources`` and ``severities`` fields list all labels present so the
    caller can build the full sparse grid.
    """
    return await get_drift_heatmap(db, days=days, source_ids=source_ids, limit=limit)


@router.get(
    "/cost-value",
    response_model=CostValueResponse,
    summary="Get cost-to-value chart",
    responses={**_R422},
)
async def get_reporting_cost_value(
    db: DbDep,
    days: Annotated[
        int,
        Query(ge=1, le=REPORTING_MAX_DAYS, description="Look-back window in days."),
    ] = REPORTING_DEFAULT_DAYS,
    source_ids: Annotated[
        list[int] | None,
        Query(description="Optional list of source IDs to filter by."),
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_PAGE_SIZE,
            description="Maximum number of sources to include.",
        ),
    ] = REPORTING_DEFAULT_COST_LIMIT,
) -> CostValueResponse:
    """Return cost-to-value chart data across sources and teams.

    For each source three cost efficiency ratios are computed over the
    selected window:

    - **cost_per_observation_usd** — spend divided by successful ingestion calls
      (calls that did not result in a breaking schema drift event).
    - **cost_per_insight_usd** — spend divided by actionable drift events
      generated (each drift event = one schema-change insight).

    Team-level summaries roll both dimensions up across all sources
    belonging to the same ``owner_team``.  Sources with no configured
    ``cost_per_call_usd`` contribute zero cost but are included for
    call-volume and insight-count visibility.
    """
    return await get_cost_value_chart(db, days=days, source_ids=source_ids, limit=limit)


@router.get(
    "/freshness-sla",
    response_model=FreshnessSLAResponse,
    summary="Get freshness SLA dashboard with incident timeline",
    responses={**_R422},
)
async def get_reporting_freshness_sla(
    db: DbDep,
    days: Annotated[
        int,
        Query(ge=1, le=REPORTING_MAX_DAYS, description="Look-back window in days."),
    ] = REPORTING_DEFAULT_DAYS,
    source_ids: Annotated[
        list[int] | None,
        Query(description="Optional list of source IDs to filter by."),
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_PAGE_SIZE,
            description="Maximum number of sources to include.",
        ),
    ] = REPORTING_DEFAULT_FRESHNESS_LIMIT,
    sla_threshold_hours: Annotated[
        int,
        Query(
            ge=1,
            le=REPORTING_MAX_SLA_THRESHOLD_HOURS,
            description=(
                "Freshness SLA threshold in hours.  A source whose last snapshot "
                "is older than this threshold is classified as breached."
            ),
        ),
    ] = REPORTING_DEFAULT_SLA_THRESHOLD_HOURS,
) -> FreshnessSLAResponse:
    """Return freshness SLA status and incident timeline per source.

    Each source row reports its last ingestion timestamp and a **status**:

    - ``ok``: last snapshot is within the SLA threshold.
    - ``warning``: last snapshot age is between 75 % and 100 % of the threshold.
    - ``breached``: last snapshot age exceeds the threshold.
    - ``no_data``: no snapshots received in the look-back window.

    The **incident timeline** lists every gap between consecutive ingestion
    snapshots that exceeded the threshold.  Open incidents (sources still
    breaching right now) appear with ``is_open: true`` and ``gap_end: null``.
    """
    return await get_freshness_sla(
        db,
        days=days,
        source_ids=source_ids,
        limit=limit,
        sla_threshold_hours=sla_threshold_hours,
    )


@router.get(
    "/executive-summary",
    response_model=ExecutiveSummaryResponse,
    summary="Get weekly executive summary",
    responses={**_R422},
)
async def get_reporting_executive_summary(
    db: DbDep,
    days: Annotated[
        int,
        Query(ge=1, le=REPORTING_MAX_DAYS, description="Look-back window in days."),
    ] = REPORTING_DEFAULT_DAYS,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_PAGE_SIZE,
            description="Maximum number of sources to include per sub-report.",
        ),
    ] = REPORTING_EXEC_SUMMARY_DEFAULT_SOURCE_LIMIT,
    sla_threshold_hours: Annotated[
        int,
        Query(
            ge=1,
            le=REPORTING_MAX_SLA_THRESHOLD_HOURS,
            description="Freshness SLA threshold in hours used for breach classification.",
        ),
    ] = REPORTING_DEFAULT_SLA_THRESHOLD_HOURS,
) -> ExecutiveSummaryResponse:
    """Return a weekly executive summary combining drift, freshness, and cost signals.

    Aggregates three BI read models into a single leadership dashboard view:

    - **Drift**: total drift events, average compatibility score, sources with
      breaking changes.
    - **Freshness**: SLA breach and warning counts, open incidents.
    - **Cost**: total spend, average cost-per-insight, highest-spend source.
    - **Action items**: prioritised list of recommended actions (critical → low)
      derived from the signals above.
    """
    return await get_executive_summary(
        db,
        days=days,
        limit=limit,
        sla_threshold_hours=sla_threshold_hours,
        max_actions=REPORTING_EXEC_SUMMARY_MAX_ACTIONS,
    )
