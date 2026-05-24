"""Repository logic for BI and reporting read models."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.reporting import (
    ActionItem,
    CohortReport,
    CostSummarySection,
    CostValueResponse,
    CostValueRow,
    DashboardPreset,
    DriftHeatmapCell,
    DriftHeatmapResponse,
    DriftSummarySection,
    ExecutiveSummaryResponse,
    ExportJob,
    ExportJobRequest,
    FreshnessIncident,
    FreshnessSLAResponse,
    FreshnessSourceRow,
    FreshnessSummarySection,
    MetricPoint,
    MetricSeries,
    TeamCostSummary,
)
from services.ingestor.constants import REPORTING_DEFAULT_EXPORT_FORMAT
from services.ingestor.models import ContractSnapshot, DriftEvent, SourceProfile


def _now_utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _cutoff_utc_naive(days: int) -> datetime:
    return _now_utc_naive() - timedelta(days=days)


async def list_metric_series(
    db: AsyncSession,
    *,
    days: int,
    source_id: int | None,
    limit: int,
) -> list[MetricSeries]:
    """Build KPI rollups from recent drift events."""
    cutoff = _cutoff_utc_naive(days)

    source_stmt = (
        select(SourceProfile)
        .where(SourceProfile.deleted_at.is_(None))
        .order_by(SourceProfile.created_at.desc())
        .limit(limit)
    )
    if source_id is not None:
        source_stmt = source_stmt.where(SourceProfile.id == source_id)

    sources = list((await db.execute(source_stmt)).scalars().all())
    if not sources:
        return []

    source_ids = [source.id for source in sources]
    event_stmt = (
        select(DriftEvent)
        .where(DriftEvent.source_id.in_(source_ids))
        .where(DriftEvent.created_at >= cutoff)
        .order_by(DriftEvent.created_at.asc())
    )
    events = list((await db.execute(event_stmt)).scalars().all())

    events_by_source: dict[int, list[DriftEvent]] = defaultdict(list)
    for event in events:
        events_by_source[event.source_id].append(event)

    series: list[MetricSeries] = []
    for source in sources:
        source_events = events_by_source.get(source.id, [])
        if not source_events:
            continue

        points = [
            MetricPoint(
                timestamp=event.created_at, value=round(event.compatibility_score, 2)
            )
            for event in source_events
        ]
        avg_score = sum(point.value for point in points) / len(points)

        series.append(
            MetricSeries(
                series_id=f"compatibility-{source.id}",
                source_id=source.id,
                source_name=source.name,
                metric="compatibility_score",
                unit="score",
                points=points,
                summary=(
                    f"Average compatibility score is {avg_score:.2f} for "
                    f"the selected {days}-day window."
                ),
            )
        )

    return series


async def list_cohort_reports(
    db: AsyncSession,
    *,
    days: int,
    limit: int,
) -> list[CohortReport]:
    """Build cohort comparison rows ranked by reliability."""
    cutoff = _cutoff_utc_naive(days)

    sources = list(
        (
            await db.execute(
                select(SourceProfile)
                .where(SourceProfile.deleted_at.is_(None))
                .order_by(SourceProfile.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    if not sources:
        return []

    source_ids = [source.id for source in sources]
    events = list(
        (
            await db.execute(
                select(DriftEvent)
                .where(DriftEvent.source_id.in_(source_ids))
                .where(DriftEvent.created_at >= cutoff)
                .order_by(DriftEvent.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    events_by_source: dict[int, list[DriftEvent]] = defaultdict(list)
    for event in events:
        events_by_source[event.source_id].append(event)

    rows: list[CohortReport] = []
    for source in sources:
        source_events = events_by_source.get(source.id, [])
        sample_size = len(source_events)

        if sample_size == 0:
            avg_compat = 100.0
            breaking_rate = 0.0
        else:
            avg_compat = (
                sum(event.compatibility_score for event in source_events) / sample_size
            )
            breaking_count = sum(
                1 for event in source_events if event.event_type == "breaking"
            )
            breaking_rate = (breaking_count / sample_size) * 100.0

        if source.sla_ms:
            avg_sla_gap_ms = max(0.0, source.sla_ms * (1.0 - (avg_compat / 100.0)))
        else:
            avg_sla_gap_ms = 0.0

        rows.append(
            CohortReport(
                cohort_id=f"cohort-source-{source.id}",
                cohort_name=f"{source.name} reliability cohort",
                source_id=source.id,
                sample_size=sample_size,
                avg_compatibility_score=round(avg_compat, 2),
                breaking_rate_pct=round(breaking_rate, 2),
                avg_sla_gap_ms=round(avg_sla_gap_ms, 2),
                rank=1,
            )
        )

    rows.sort(
        key=lambda item: (
            -item.avg_compatibility_score,
            item.breaking_rate_pct,
            item.source_id,
        )
    )
    for index, row in enumerate(rows, start=1):
        row.rank = index

    return rows


def list_dashboard_presets() -> list[DashboardPreset]:
    """Return built-in dashboard presets for BI consumers."""
    return [
        DashboardPreset(
            preset_id="ops-scorecard",
            name="Operations Scorecard",
            description="Daily operational view for reliability engineering and on-call teams.",
            widgets=[
                "provider_uptime",
                "compatibility_trend",
                "breaking_drift_heatmap",
                "delivery_suppression_ratio",
            ],
        ),
        DashboardPreset(
            preset_id="exec-weekly-summary",
            name="Executive Weekly Summary",
            description="Weekly leadership dashboard focused on risk and cost-to-value trends.",
            widgets=[
                "error_budget_burn",
                "cohort_ranking",
                "cost_to_value_ratio",
                "top_recommendations",
            ],
        ),
    ]


def create_export_job(payload: ExportJobRequest) -> ExportJob:
    """Create a deterministic export job response for current BI slice."""
    created_at = _now_utc_naive()
    export_format = payload.export_format or REPORTING_DEFAULT_EXPORT_FORMAT

    return ExportJob(
        export_id=f"export-{int(created_at.timestamp())}",
        status="completed",
        preset_id=payload.preset_id,
        export_format=export_format,
        created_at=created_at,
        detail="Export generated from reporting read models.",
    )


# Canonical severity order for consistent heatmap column rendering.
_SEVERITY_ORDER: list[str] = ["critical", "high", "medium", "low", "none"]


async def get_drift_heatmap(
    db: AsyncSession,
    *,
    days: int,
    source_ids: list[int] | None,
    limit: int,
) -> DriftHeatmapResponse:
    """Build a sparse drift heatmap keyed by (source, severity).

    Queries ``drift_events`` in the given window, groups counts by
    (source_id, severity), then normalises each cell's count against the
    maximum observed count to produce a heat_value in [0.0, 1.0].
    Only cells with at least one event are included; the caller builds
    the full grid using the ``sources`` and ``severities`` label lists.
    """
    cutoff = _cutoff_utc_naive(days)

    source_stmt = (
        select(SourceProfile)
        .where(SourceProfile.deleted_at.is_(None))
        .order_by(SourceProfile.created_at.desc())
        .limit(limit)
    )
    if source_ids:
        source_stmt = source_stmt.where(SourceProfile.id.in_(source_ids))

    sources = list((await db.execute(source_stmt)).scalars().all())
    if not sources:
        return DriftHeatmapResponse(
            sources=[],
            severities=[],
            cells=[],
            total_events=0,
            window_days=days,
        )

    queried_source_ids = [source.id for source in sources]

    event_stmt = (
        select(DriftEvent)
        .where(DriftEvent.source_id.in_(queried_source_ids))
        .where(DriftEvent.created_at >= cutoff)
    )
    events = list((await db.execute(event_stmt)).scalars().all())

    # Accumulate counts per (source_id, severity) pair.
    counts: dict[tuple[int, str], int] = defaultdict(int)
    for event in events:
        counts[(event.source_id, event.severity)] += 1

    if not counts:
        return DriftHeatmapResponse(
            sources=[],
            severities=[],
            cells=[],
            total_events=0,
            window_days=days,
        )

    max_count = max(counts.values())

    # Build cells sorted by source creation order then severity order.
    cells: list[DriftHeatmapCell] = []
    seen_sources: list[str] = []
    seen_severities: set[str] = set()

    for source in sources:
        source_added = False
        for severity in _SEVERITY_ORDER:
            count = counts.get((source.id, severity), 0)
            if count == 0:
                continue
            if not source_added:
                seen_sources.append(source.name)
                source_added = True
            seen_severities.add(severity)
            cells.append(
                DriftHeatmapCell(
                    source_id=source.id,
                    source_name=source.name,
                    severity=severity,
                    count=count,
                    heat_value=round(count / max_count, 4),
                )
            )

    severities_ordered = [s for s in _SEVERITY_ORDER if s in seen_severities]

    return DriftHeatmapResponse(
        sources=seen_sources,
        severities=severities_ordered,
        cells=cells,
        total_events=len(events),
        window_days=days,
    )


async def get_cost_value_chart(
    db: AsyncSession,
    *,
    days: int,
    source_ids: list[int] | None,
    limit: int,
) -> CostValueResponse:
    """Build cost-to-value rows per source and team-level summaries.

    Three dimensions are computed for each source:

    - **cost_per_record_usd**: total spend divided by the number of
      ingestion calls (snapshots) that did *not* produce a breaking drift
      event.  Breaking calls still cost money but deliver no usable record.
    - **cost_per_insight_usd**: total spend divided by the number of drift
      events generated — each event is one actionable schema-change insight.
    - Team rollups aggregate both dimensions across all sources belonging
      to the same ``owner_team``.

    Sources without a configured ``cost_per_call_usd`` contribute zero cost
    but are still included so callers can see call volume and insight counts.
    """
    cutoff = _cutoff_utc_naive(days)

    source_stmt = (
        select(SourceProfile)
        .where(SourceProfile.deleted_at.is_(None))
        .order_by(SourceProfile.created_at.desc())
        .limit(limit)
    )
    if source_ids:
        source_stmt = source_stmt.where(SourceProfile.id.in_(source_ids))

    sources = list((await db.execute(source_stmt)).scalars().all())
    if not sources:
        return CostValueResponse(
            rows=[],
            team_summaries=[],
            total_cost_usd=0.0,
            window_days=days,
        )

    queried_source_ids = [s.id for s in sources]

    # Fetch all snapshots in window (each snapshot == one ingestion call).
    snapshots = list(
        (
            await db.execute(
                select(ContractSnapshot)
                .where(ContractSnapshot.source_id.in_(queried_source_ids))
                .where(ContractSnapshot.created_at >= cutoff)
            )
        )
        .scalars()
        .all()
    )

    # Fetch all drift events in window.
    drift_events = list(
        (
            await db.execute(
                select(DriftEvent)
                .where(DriftEvent.source_id.in_(queried_source_ids))
                .where(DriftEvent.created_at >= cutoff)
            )
        )
        .scalars()
        .all()
    )

    # Index: snapshot_ids that produced a breaking event (cost but no good record).
    breaking_snapshot_ids: set[int] = {
        event.current_snapshot_id
        for event in drift_events
        if event.event_type == "breaking"
    }

    snapshots_by_source: dict[int, list[ContractSnapshot]] = defaultdict(list)
    for snapshot in snapshots:
        snapshots_by_source[snapshot.source_id].append(snapshot)

    insights_by_source: dict[int, int] = defaultdict(int)
    for event in drift_events:
        insights_by_source[event.source_id] += 1

    rows: list[CostValueRow] = []
    for source in sources:
        source_snapshots = snapshots_by_source.get(source.id, [])
        total_calls = len(source_snapshots)

        breaking_calls = sum(
            1 for s in source_snapshots if s.id in breaking_snapshot_ids
        )
        successful_records = total_calls - breaking_calls
        insights = insights_by_source.get(source.id, 0)

        unit_cost = source.cost_per_call_usd or 0.0
        total_cost = round(unit_cost * total_calls, 6)

        cost_per_record: float | None = None
        if successful_records > 0 and total_cost > 0:
            cost_per_record = round(total_cost / successful_records, 6)

        cost_per_insight: float | None = None
        if insights > 0 and total_cost > 0:
            cost_per_insight = round(total_cost / insights, 6)

        rows.append(
            CostValueRow(
                source_id=source.id,
                source_name=source.name,
                owner_team=source.owner_team,
                cost_per_call_usd=unit_cost,
                total_calls=total_calls,
                total_cost_usd=total_cost,
                successful_records=successful_records,
                insights_generated=insights,
                cost_per_record_usd=cost_per_record,
                cost_per_insight_usd=cost_per_insight,
            )
        )

    rows.sort(key=lambda r: (-r.total_cost_usd, r.source_id))

    # Build team summaries.
    team_totals: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {"cost": 0.0, "calls": 0, "insights": 0}
    )
    for row in rows:
        team = row.owner_team or "unassigned"
        team_totals[team]["cost"] = round(
            float(team_totals[team]["cost"]) + row.total_cost_usd, 6
        )
        team_totals[team]["calls"] = int(team_totals[team]["calls"]) + row.total_calls
        team_totals[team]["insights"] = (
            int(team_totals[team]["insights"]) + row.insights_generated
        )

    team_summaries: list[TeamCostSummary] = []
    for team, totals in team_totals.items():
        t_cost = float(totals["cost"])
        t_insights = int(totals["insights"])
        team_summaries.append(
            TeamCostSummary(
                team=team,
                total_cost_usd=t_cost,
                total_calls=int(totals["calls"]),
                total_insights=t_insights,
                cost_per_insight_usd=(
                    round(t_cost / t_insights, 6)
                    if t_insights > 0 and t_cost > 0
                    else None
                ),
            )
        )
    team_summaries.sort(key=lambda ts: (-ts.total_cost_usd, ts.team))

    grand_total = round(sum(r.total_cost_usd for r in rows), 6)

    return CostValueResponse(
        rows=rows,
        team_summaries=team_summaries,
        total_cost_usd=grand_total,
        window_days=days,
    )


def _freshness_status(age_seconds: int | None, threshold_seconds: int) -> str:
    if age_seconds is None:
        return "no_data"
    if age_seconds > threshold_seconds:
        return "breached"
    if age_seconds > int(threshold_seconds * 0.75):
        return "warning"
    return "ok"


async def get_freshness_sla(
    db: AsyncSession,
    *,
    days: int,
    source_ids: list[int] | None,
    limit: int,
    sla_threshold_hours: int,
) -> FreshnessSLAResponse:
    """Compute freshness SLA status and incident timeline per source.

    For each matched source the function:
    1. Finds the most recent ``ContractSnapshot`` and computes its age.
    2. Classifies the source as ``ok``, ``warning``, ``breached``, or
       ``no_data`` relative to ``sla_threshold_hours``.
    3. Scans consecutive snapshot pairs within the window for gaps that
       exceeded the threshold — each such gap becomes an
       ``FreshnessIncident`` in the timeline.
    """
    threshold_seconds = sla_threshold_hours * 3600
    now = _now_utc_naive()
    cutoff = now - timedelta(days=days)

    source_stmt = (
        select(SourceProfile)
        .where(SourceProfile.deleted_at.is_(None))
        .order_by(SourceProfile.name.asc())
        .limit(limit)
    )
    if source_ids:
        source_stmt = source_stmt.where(SourceProfile.id.in_(source_ids))

    sources = list((await db.execute(source_stmt)).scalars().all())
    if not sources:
        return FreshnessSLAResponse(
            sources=[],
            incidents=[],
            total_breached=0,
            total_ok=0,
            total_no_data=0,
            window_days=days,
            sla_threshold_hours=sla_threshold_hours,
        )

    sid_to_source: dict[int, SourceProfile] = {s.id: s for s in sources}
    queried_ids = list(sid_to_source.keys())

    snap_stmt = (
        select(ContractSnapshot.source_id, ContractSnapshot.created_at)
        .where(
            ContractSnapshot.source_id.in_(queried_ids),
            ContractSnapshot.created_at >= cutoff,
        )
        .order_by(ContractSnapshot.source_id, ContractSnapshot.created_at.asc())
    )
    rows_raw = list((await db.execute(snap_stmt)).all())

    # Group snapshots by source_id; each list is already sorted ascending by created_at
    snaps_by_source: dict[int, list[datetime]] = defaultdict(list)
    for source_id, created_at in rows_raw:
        snaps_by_source[source_id].append(created_at)

    source_rows: list[FreshnessSourceRow] = []
    all_incidents: list[FreshnessIncident] = []

    for src in sources:
        snaps = snaps_by_source.get(src.id, [])
        last_at = snaps[-1] if snaps else None

        age_s = int((now - last_at).total_seconds()) if last_at is not None else None

        status = _freshness_status(age_s, threshold_seconds)

        # Build incident list: consecutive gaps + potential open tail
        incidents_for_source: list[FreshnessIncident] = []
        for i in range(len(snaps) - 1):
            gap_s = int((snaps[i + 1] - snaps[i]).total_seconds())
            if gap_s > threshold_seconds:
                incidents_for_source.append(
                    FreshnessIncident(
                        source_id=src.id,
                        source_name=src.name,
                        gap_start=snaps[i],
                        gap_end=snaps[i + 1],
                        gap_seconds=gap_s,
                        is_open=False,
                    )
                )

        # Open incident: last snapshot is too old (or no snapshots at all)
        if status == "breached":
            open_start = last_at if last_at is not None else cutoff
            open_gap_s = int((now - open_start).total_seconds())
            incidents_for_source.append(
                FreshnessIncident(
                    source_id=src.id,
                    source_name=src.name,
                    gap_start=open_start,
                    gap_end=None,
                    gap_seconds=open_gap_s,
                    is_open=True,
                )
            )

        all_incidents.extend(incidents_for_source)
        source_rows.append(
            FreshnessSourceRow(
                source_id=src.id,
                source_name=src.name,
                owner_team=src.owner_team,
                last_snapshot_at=last_at,
                age_seconds=age_s,
                sla_threshold_seconds=threshold_seconds,
                status=status,
                total_snapshots=len(snaps),
                incident_count=len(incidents_for_source),
            )
        )

    # Incidents sorted newest-first (by gap_start desc)
    all_incidents.sort(key=lambda inc: inc.gap_start, reverse=True)

    total_breached = sum(1 for r in source_rows if r.status == "breached")
    total_ok = sum(1 for r in source_rows if r.status in ("ok", "warning"))
    total_no_data = sum(1 for r in source_rows if r.status == "no_data")

    return FreshnessSLAResponse(
        sources=source_rows,
        incidents=all_incidents,
        total_breached=total_breached,
        total_ok=total_ok,
        total_no_data=total_no_data,
        window_days=days,
        sla_threshold_hours=sla_threshold_hours,
    )


# Priority sort key: lower value → higher urgency.
_ACTION_PRIORITY_ORDER: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}


async def get_executive_summary(
    db: AsyncSession,
    *,
    days: int,
    limit: int,
    sla_threshold_hours: int,
    max_actions: int,
) -> ExecutiveSummaryResponse:
    """Build a weekly executive summary from drift, freshness, and cost signals.

    Runs three read-model queries concurrently then synthesises the results
    into headline KPIs and a prioritised action list.
    """
    cohorts, freshness, cost = await asyncio.gather(
        list_cohort_reports(db, days=days, limit=limit),
        get_freshness_sla(
            db,
            days=days,
            source_ids=None,
            limit=limit,
            sla_threshold_hours=sla_threshold_hours,
        ),
        get_cost_value_chart(db, days=days, source_ids=None, limit=limit),
    )

    # --- Drift summary ---
    sources_with_drift = [c for c in cohorts if c.sample_size > 0]
    total_events = sum(c.sample_size for c in sources_with_drift)
    avg_compat = (
        sum(c.avg_compatibility_score for c in sources_with_drift)
        / len(sources_with_drift)
        if sources_with_drift
        else 100.0
    )
    breaking_source_count = sum(1 for c in cohorts if c.breaking_rate_pct > 0.0)
    drift_summary = DriftSummarySection(
        total_sources_with_drift=len(sources_with_drift),
        total_events=total_events,
        avg_compatibility_score=round(avg_compat, 2),
        breaking_source_count=breaking_source_count,
    )

    # --- Freshness summary ---
    open_incidents = sum(1 for inc in freshness.incidents if inc.is_open)
    freshness_summary = FreshnessSummarySection(
        total_sources=len(freshness.sources),
        breached=freshness.total_breached,
        warning=sum(1 for s in freshness.sources if s.status == "warning"),
        ok=freshness.total_ok,
        no_data=freshness.total_no_data,
        open_incidents=open_incidents,
    )

    # --- Cost summary ---
    rows_with_spend = [r for r in cost.rows if r.total_cost_usd > 0]
    avg_cost_per_insight: float | None = None
    if rows_with_spend:
        total_insights_with_spend = sum(r.insights_generated for r in rows_with_spend)
        total_spend = sum(r.total_cost_usd for r in rows_with_spend)
        if total_insights_with_spend > 0:
            avg_cost_per_insight = round(total_spend / total_insights_with_spend, 6)
    highest_cost_source = cost.rows[0].source_name if cost.rows else None
    cost_summary = CostSummarySection(
        total_cost_usd=cost.total_cost_usd,
        total_sources=len(cost.rows),
        avg_cost_per_insight_usd=avg_cost_per_insight,
        highest_cost_source_name=highest_cost_source,
    )

    # --- Build action items ---
    actions: list[ActionItem] = []

    # Drift-based actions derived from cohort reliability data.
    for cohort in cohorts:
        if cohort.breaking_rate_pct >= 30.0:
            actions.append(
                ActionItem(
                    priority="high",
                    category="drift",
                    title=f"High breaking drift rate: {cohort.cohort_name}",
                    description=(
                        f"{cohort.breaking_rate_pct:.1f}% of schema events were breaking "
                        f"(avg compatibility score: {cohort.avg_compatibility_score:.1f}). "
                        "Review schema evolution policy and add compatibility gates."
                    ),
                    source_id=cohort.source_id,
                    source_name=None,
                )
            )
        elif cohort.breaking_rate_pct > 0.0 and cohort.avg_compatibility_score < 70.0:
            actions.append(
                ActionItem(
                    priority="medium",
                    category="drift",
                    title=f"Schema drift detected: {cohort.cohort_name}",
                    description=(
                        f"Compatibility score is {cohort.avg_compatibility_score:.1f} with "
                        f"{cohort.breaking_rate_pct:.1f}% breaking rate. "
                        "Investigate upstream schema changes."
                    ),
                    source_id=cohort.source_id,
                    source_name=None,
                )
            )

    # Freshness-based actions derived from SLA status.
    for src in freshness.sources:
        if src.status == "breached":
            hours_stale = (src.age_seconds or 0) // 3600
            actions.append(
                ActionItem(
                    priority="critical",
                    category="freshness",
                    title=f"SLA breach: {src.source_name}",
                    description=(
                        f"No fresh data received for {hours_stale}h "
                        f"(threshold: {sla_threshold_hours}h). "
                        "Check ingestion pipeline and upstream API availability."
                    ),
                    source_id=src.source_id,
                    source_name=src.source_name,
                )
            )
        elif src.status == "warning":
            hours_stale = (src.age_seconds or 0) // 3600
            actions.append(
                ActionItem(
                    priority="medium",
                    category="freshness",
                    title=f"Freshness warning: {src.source_name}",
                    description=(
                        f"Last snapshot is {hours_stale}h old, "
                        f"approaching the {sla_threshold_hours}h SLA threshold. "
                        "Monitor ingestion frequency."
                    ),
                    source_id=src.source_id,
                    source_name=src.source_name,
                )
            )

    # Cost-based actions: flag the highest cost-per-insight outlier.
    cost_rows_with_insight = [
        r for r in cost.rows if r.cost_per_insight_usd is not None
    ]
    if cost_rows_with_insight:
        max_cpi = max(r.cost_per_insight_usd for r in cost_rows_with_insight)  # type: ignore[type-var]
        for row in cost_rows_with_insight:
            if (
                row.cost_per_insight_usd is not None
                and row.cost_per_insight_usd >= max_cpi * 0.8
            ):
                actions.append(
                    ActionItem(
                        priority="low",
                        category="cost",
                        title=f"High cost-per-insight: {row.source_name}",
                        description=(
                            f"${row.cost_per_insight_usd:.4f} per insight with "
                            f"${row.total_cost_usd:.4f} total spend in window. "
                            "Consider optimising polling frequency or schema validation logic."
                        ),
                        source_id=row.source_id,
                        source_name=row.source_name,
                    )
                )

    actions.sort(
        key=lambda a: (_ACTION_PRIORITY_ORDER.get(a.priority, 99), a.source_id or 0)
    )
    actions = actions[:max_actions]

    return ExecutiveSummaryResponse(
        generated_at=_now_utc_naive(),
        window_days=days,
        drift=drift_summary,
        freshness=freshness_summary,
        cost=cost_summary,
        action_items=actions,
        total_actions=len(actions),
    )
