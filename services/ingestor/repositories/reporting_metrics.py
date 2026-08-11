"""Metric series and cohort report read models."""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.reporting import (
    CohortReport,
    MetricPoint,
    MetricSeries,
)
from services.ingestor.models import DriftEvent, SourceProfile
from services.ingestor.repositories.reporting_utils import _cutoff_utc_naive


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

        if source.latency_threshold_ms:
            avg_sla_gap_ms = max(
                0.0,
                source.latency_threshold_ms * (1.0 - (avg_compat / 100.0)),
            )
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
