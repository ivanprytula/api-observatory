"""Freshness SLA read model."""

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.reporting import (
    FreshnessIncident,
    FreshnessSLAResponse,
    FreshnessSourceRow,
)
from services.ingestor.models import ContractSnapshot, SourceProfile
from services.ingestor.repositories.reporting_utils import (
    _now_utc_naive,
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
    """Compute freshness SLA status and incident timeline per source."""
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
                owner_team=None,
                last_snapshot_at=last_at,
                age_seconds=age_s,
                sla_threshold_seconds=threshold_seconds,
                status=status,
                total_snapshots=len(snaps),
                incident_count=len(incidents_for_source),
            )
        )

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
