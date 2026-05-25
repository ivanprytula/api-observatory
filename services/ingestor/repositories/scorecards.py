"""Repository helpers for provider health samples and scorecard computation.

Aggregation strategy
--------------------
All rolling-window statistics (uptime %, p50/p95 latency, error count) are
computed inside a single PostgreSQL aggregate query using:

    COUNT(*) FILTER (WHERE NOT is_success)
    AVG(latency_ms)
    PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY latency_ms)
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms)

This keeps row fetching to a minimum and delegates percentile math to the
database engine, which uses the Greenwald-Khanna algorithm rather than
pulling every raw sample into Python.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Row, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.scorecards import (
    HealthSampleCreate,
    HealthSampleResponse,
    ProviderScorecard,
)
from services.ingestor.constants import SCORECARD_DEFAULT_SLO_TARGET_PCT
from services.ingestor.models import ProviderHealthSample, SourceProfile


def _now_utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _cutoff_utc_naive(days: int) -> datetime:
    return _now_utc_naive() - timedelta(days=days)


async def record_health_sample(
    db: AsyncSession,
    payload: HealthSampleCreate,
) -> HealthSampleResponse:
    """Persist one provider health probe result and return its representation."""
    sample = ProviderHealthSample(
        source_id=payload.source_id,
        sampled_at=payload.sampled_at.replace(tzinfo=None),
        latency_ms=payload.latency_ms,
        is_success=payload.is_success,
        http_status=payload.http_status,
        response_body_hash=payload.response_body_hash,
        error_message=payload.error_message,
        region=payload.region,
        tenant_id=payload.tenant_id,
    )
    db.add(sample)
    await db.flush()
    await db.refresh(sample)
    await db.commit()
    return HealthSampleResponse.model_validate(sample)


def _scorecard_from_agg(
    source: SourceProfile,
    *,
    window_days: int,
    slo_target_pct: float,
    sample_count: int,
    error_count: int,
    avg_latency_ms: float,
    p50_latency_ms: float,
    p95_latency_ms: float,
) -> ProviderScorecard:
    """Assemble a ProviderScorecard from pre-aggregated SQL results.

    All numeric inputs come directly from the database aggregate query.
    Business metric derivation (uptime %, burn rate) happens here because
    those are lightweight formulas over already-aggregated scalars.
    """
    if sample_count == 0:
        uptime_pct = 100.0
        error_rate = 0.0
    else:
        uptime_pct = (sample_count - error_count) / sample_count * 100.0
        error_rate = 1.0 - uptime_pct / 100.0

    error_budget = 1.0 - slo_target_pct / 100.0
    # Avoid division by zero when SLO target is 100% (zero error budget).
    if error_budget <= 0.0:
        burn_rate = 0.0 if error_rate == 0.0 else float("inf")
    else:
        burn_rate = error_rate / error_budget

    return ProviderScorecard(
        source_id=source.id,
        source_name=source.name,
        window_days=window_days,
        sample_count=sample_count,
        error_count=error_count,
        uptime_pct=round(uptime_pct, 4),
        avg_latency_ms=round(avg_latency_ms, 2),
        p50_latency_ms=round(p50_latency_ms, 2),
        p95_latency_ms=round(p95_latency_ms, 2),
        slo_target_pct=slo_target_pct,
        error_budget_burn_rate=round(burn_rate, 4),
        generated_at=_now_utc_naive(),
    )


async def get_scorecard(
    db: AsyncSession,
    source_id: int,
    *,
    days: int,
    slo_target_pct: float = SCORECARD_DEFAULT_SLO_TARGET_PCT,
) -> ProviderScorecard | None:
    """Return a scorecard for one source, or None if the source does not exist."""
    source_result = await db.execute(
        select(SourceProfile).where(
            SourceProfile.id == source_id,
            SourceProfile.deleted_at.is_(None),
        )
    )
    source = source_result.scalar_one_or_none()
    if source is None:
        return None

    cutoff = _cutoff_utc_naive(days)
    row = _extract_agg(await db.execute(_agg_query([source_id], cutoff)), source_id)
    return _scorecard_from_agg(
        source,
        window_days=days,
        slo_target_pct=slo_target_pct,
        **_row_to_kwargs(row),
    )


def _agg_query(source_ids: list[int], cutoff: datetime):  # type: ignore[return]
    """Single GROUP BY query: one row per source with COUNT/AVG/PERCENTILE_CONT.

    Returns COUNT(*) FILTER for error count and PERCENTILE_CONT(0.5/0.95)
    for median and p95 latency — all computed inside PostgreSQL.
    """
    return (
        select(
            ProviderHealthSample.source_id,
            func.count().label("sample_count"),
            func.count()
            .filter(ProviderHealthSample.is_success.is_(False))
            .label("error_count"),
            func.avg(ProviderHealthSample.latency_ms).label("avg_latency_ms"),
            func.percentile_cont(0.5)
            .within_group(ProviderHealthSample.latency_ms.asc())
            .label("p50_latency_ms"),
            func.percentile_cont(0.95)
            .within_group(ProviderHealthSample.latency_ms.asc())
            .label("p95_latency_ms"),
        )
        .where(
            ProviderHealthSample.source_id.in_(source_ids),
            ProviderHealthSample.sampled_at >= cutoff,
        )
        .group_by(ProviderHealthSample.source_id)
    )


def _extract_agg(result: Any, source_id: int) -> Row[Any] | None:
    """Index aggregate result rows by source_id; return row or None."""
    return {row.source_id: row for row in result.all()}.get(source_id)


def _row_to_kwargs(row: Row[Any] | None) -> dict[str, Any]:
    """Convert a nullable aggregate row to _scorecard_from_agg keyword args."""
    if row is None:
        return {
            "sample_count": 0,
            "error_count": 0,
            "avg_latency_ms": 0.0,
            "p50_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
        }
    return {
        "sample_count": row.sample_count or 0,
        "error_count": row.error_count or 0,
        "avg_latency_ms": float(row.avg_latency_ms)
        if row.avg_latency_ms is not None
        else 0.0,
        "p50_latency_ms": float(row.p50_latency_ms)
        if row.p50_latency_ms is not None
        else 0.0,
        "p95_latency_ms": float(row.p95_latency_ms)
        if row.p95_latency_ms is not None
        else 0.0,
    }


async def list_scorecards(
    db: AsyncSession,
    *,
    days: int,
    source_id: int | None,
    slo_target_pct: float,
    limit: int,
) -> list[ProviderScorecard]:
    """Compute scorecards for all active sources via one aggregate SQL query.

    Two queries total regardless of source count:
      1. Fetch active SourceProfile rows (with LIMIT).
      2. One GROUP BY aggregate over all matching health samples.
    """
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

    cutoff = _cutoff_utc_naive(days)
    source_ids = [s.id for s in sources]
    agg_rows = {
        row.source_id: row
        for row in (await db.execute(_agg_query(source_ids, cutoff))).all()
    }

    scorecards = []
    for source in sources:
        row = agg_rows.get(source.id)
        scorecards.append(
            _scorecard_from_agg(
                source,
                window_days=days,
                slo_target_pct=slo_target_pct,
                **_row_to_kwargs(row),
            )
        )
    return scorecards
