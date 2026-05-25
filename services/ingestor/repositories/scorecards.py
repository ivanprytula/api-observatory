"""Repository helpers for provider health samples and scorecard computation."""

from __future__ import annotations

import statistics
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
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


def _compute_percentile(sorted_values: list[float], pct: float) -> float:
    """Return the p-th percentile from a pre-sorted list using nearest-rank."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    rank = max(1, round(pct / 100.0 * n))
    return sorted_values[min(rank, n) - 1]


def _build_scorecard(
    source: SourceProfile,
    samples: list[ProviderHealthSample],
    *,
    window_days: int,
    slo_target_pct: float,
) -> ProviderScorecard:
    """Compute a single scorecard from raw samples for one source."""
    sample_count = len(samples)
    error_count = sum(1 for s in samples if not s.is_success)

    if sample_count == 0:
        uptime_pct = 100.0
        avg_lat = 0.0
        p50_lat = 0.0
        p95_lat = 0.0
    else:
        uptime_pct = (sample_count - error_count) / sample_count * 100.0
        latencies = sorted(s.latency_ms for s in samples)
        avg_lat = statistics.mean(latencies)
        p50_lat = _compute_percentile(latencies, 50)
        p95_lat = _compute_percentile(latencies, 95)

    error_rate = 1.0 - uptime_pct / 100.0
    error_budget = 1.0 - slo_target_pct / 100.0
    # Avoid division by zero when SLO is 100% (budget = 0)
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
        avg_latency_ms=round(avg_lat, 2),
        p50_latency_ms=round(p50_lat, 2),
        p95_latency_ms=round(p95_lat, 2),
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
    samples_result = await db.execute(
        select(ProviderHealthSample)
        .where(
            ProviderHealthSample.source_id == source_id,
            ProviderHealthSample.sampled_at >= cutoff,
        )
        .order_by(ProviderHealthSample.sampled_at.asc())
    )
    samples = list(samples_result.scalars().all())

    return _build_scorecard(
        source, samples, window_days=days, slo_target_pct=slo_target_pct
    )


async def list_scorecards(
    db: AsyncSession,
    *,
    days: int,
    source_id: int | None,
    slo_target_pct: float,
    limit: int,
) -> list[ProviderScorecard]:
    """Compute scorecards for all active sources (optionally filtered by source)."""
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

    samples_result = await db.execute(
        select(ProviderHealthSample)
        .where(
            ProviderHealthSample.source_id.in_(source_ids),
            ProviderHealthSample.sampled_at >= cutoff,
        )
        .order_by(ProviderHealthSample.sampled_at.asc())
    )
    all_samples = list(samples_result.scalars().all())

    samples_by_source: dict[int, list[ProviderHealthSample]] = {
        s.id: [] for s in sources
    }
    for sample in all_samples:
        samples_by_source[sample.source_id].append(sample)

    return [
        _build_scorecard(
            source,
            samples_by_source[source.id],
            window_days=days,
            slo_target_pct=slo_target_pct,
        )
        for source in sources
    ]
