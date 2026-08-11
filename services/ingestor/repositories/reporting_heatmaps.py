"""Drift heatmap read model."""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.reporting import (
    DriftHeatmapCell,
    DriftHeatmapResponse,
)
from services.ingestor.models import DriftEvent, SourceProfile
from services.ingestor.repositories.reporting_utils import _cutoff_utc_naive


_SEVERITY_ORDER: list[str] = ["critical", "high", "medium", "low", "none"]


async def get_drift_heatmap(
    db: AsyncSession,
    *,
    days: int,
    source_ids: list[int] | None,
    limit: int,
) -> DriftHeatmapResponse:
    """Build a sparse drift heatmap keyed by (source, severity)."""
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
