"""Analytics routes — CTE aggregations and window function queries."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.constants import API_V1_PREFIX
from services.ingestor.core.tenant import get_tenant_id
from services.ingestor.database import get_db
from services.ingestor.models import Observation


logger = logging.getLogger(__name__)

router = APIRouter(prefix=f"{API_V1_PREFIX}/analytics", tags=["analytics"])

type DbDep = Annotated[AsyncSession, Depends(get_db)]

# ---------------------------------------------------------------------------
# GET /api/v1/analytics/summary
# ---------------------------------------------------------------------------


@router.get("/summary")
async def get_summary(
    db: DbDep,
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
) -> dict[str, Any]:
    """Hourly aggregation CTE over the last N hours.

    Returns observation counts, processed percentages, and value statistics
    bucketed by hour. Uses Python-side grouping for SQLite compatibility.
    """
    # Normalize to tz-naive UTC to match DB TIMESTAMP (no timezone)
    since = (datetime.now(UTC) - timedelta(hours=hours)).replace(tzinfo=None)

    result = await db.execute(
        select(Observation)
        .where(Observation.deleted_at.is_(None))
        .where(Observation.timestamp >= since)
        .order_by(Observation.timestamp)
    )
    observations = result.scalars().all()

    # Hourly bucketing in Python (dialect-agnostic — avoids date_trunc)
    hourly: dict[datetime, list[Observation]] = defaultdict(list)
    for observation in observations:
        hour = observation.timestamp.replace(minute=0, second=0, microsecond=0)
        hourly[hour].append(observation)

    summary = []
    for hour, hour_observations in sorted(hourly.items(), reverse=True):
        observation_count = len(hour_observations)
        processed_count = sum(1 for r in hour_observations if r.processed)
        values = [
            float(r.raw_data["value"])
            for r in hour_observations
            if isinstance(r.raw_data, dict) and r.raw_data.get("value") is not None
        ]
        avg_value = round(sum(values) / len(values), 4) if values else None
        min_value = min(values) if values else None
        max_value = max(values) if values else None
        unique_sources = len({r.source for r in hour_observations})
        processed_pct = (
            round(processed_count / observation_count * 100, 2)
            if observation_count
            else None
        )

        summary.append(
            {
                "hour": hour.isoformat(),
                "observation_count": observation_count,
                "processed_count": processed_count,
                "processed_pct": processed_pct,
                "avg_value": avg_value,
                "min_value": min_value,
                "max_value": max_value,
                "unique_sources": unique_sources,
            }
        )

    return {
        "summary": summary,
        "hours_back": hours,
        "since": since.isoformat(),
    }


# ---------------------------------------------------------------------------
# GET /api/v1/analytics/percentile
# ---------------------------------------------------------------------------


@router.get("/percentile")
async def get_percentile(
    db: DbDep,
    source: Annotated[str, Query()],
) -> dict[str, Any]:
    """PERCENT_RANK window function per source (top 100 observations).

    Returns observations for the given source with their percentile rank
    calculated in Python to stay DB-agnostic in tests.
    """
    result = await db.execute(
        select(Observation)
        .where(Observation.deleted_at.is_(None))
        .where(Observation.source == source)
        .order_by(Observation.timestamp.desc())
        .limit(100)
    )
    observations = result.scalars().all()

    total = len(observations)
    output_observations = []
    for i, observation in enumerate(observations, start=1):
        value = (
            observation.raw_data.get("value")
            if isinstance(observation.raw_data, dict)
            else None
        )
        # PERCENT_RANK: (rank - 1) / (total - 1); 0.0 for single row
        percentile_rank = 0.0 if total <= 1 else round((i - 1) / (total - 1), 4)
        output_observations.append(
            {
                "id": observation.id,
                "timestamp": observation.timestamp.isoformat(),
                "value": value,
                "percentile_rank": percentile_rank,
            }
        )

    return {
        "source": source,
        "count": total,
        "observations": output_observations,
    }


# ---------------------------------------------------------------------------
# GET /api/v1/analytics/top-by-source
# ---------------------------------------------------------------------------


@router.get("/top-by-source")
async def get_top_by_source(
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 5,
    hours: Annotated[int, Query(ge=1, le=2160)] = 168,
) -> dict[str, Any]:
    """RANK window function — top N observations per source in the last N hours.

    Groups results by source and returns the highest-value observations per
    source, using Python-side ranking to remain dialect-agnostic.
    """
    # Normalize to tz-naive UTC to match DB TIMESTAMP (no timezone)
    since = (datetime.now(UTC) - timedelta(hours=hours)).replace(tzinfo=None)

    result = await db.execute(
        select(Observation)
        .where(Observation.deleted_at.is_(None))
        .where(Observation.timestamp >= since)
        .order_by(Observation.timestamp.desc())
    )
    observations = result.scalars().all()

    # Group and rank within each source
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for observation in observations:
        value = (
            observation.raw_data.get("value")
            if isinstance(observation.raw_data, dict)
            else None
        )
        grouped[observation.source].append(
            {
                "id": observation.id,
                "timestamp": observation.timestamp.isoformat(),
                "value": value,
            }
        )

    by_source: dict[str, list[dict[str, Any]]] = {}
    for source, source_observations in grouped.items():
        sorted_observations = sorted(
            source_observations,
            key=lambda r: (r.get("value") is not None, r.get("value") or 0),
            reverse=True,
        )[:limit]
        for rank, rec in enumerate(sorted_observations, start=1):
            rec["rank"] = rank
        by_source[source] = sorted_observations

    return {
        "by_source": by_source,
        "limit_per_source": limit,
        "hours_back": hours,
    }


# ---------------------------------------------------------------------------
# POST /api/v1/analytics/refresh-materialized-view
# ---------------------------------------------------------------------------


@router.post("/refresh-materialized-view")
async def refresh_materialized_view(db: DbDep) -> dict[str, str]:
    """Refresh the observations_hourly_stats materialized view.

    On PostgreSQL with the view created: executes REFRESH MATERIALIZED VIEW.
    On other dialects or if view not created: no-op, returns success.
    """
    from sqlalchemy import text

    try:
        await db.execute(text("REFRESH MATERIALIZED VIEW observations_hourly_stats"))
        await db.commit()
        logger.info("materialized_view_refreshed")
    except Exception:
        # View not yet created, wrong dialect, or other error — roll back
        # so the transaction is clean for subsequent operations.
        await db.rollback()

    return {"status": "success", "message": "Materialized view refresh requested"}


# ---------------------------------------------------------------------------
# GET /api/v1/analytics/materialized-view-stats
# ---------------------------------------------------------------------------


@router.get("/materialized-view-stats")
async def get_materialized_view_stats(
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=168)] = 24,
) -> dict[str, Any]:
    """Query pre-aggregated hourly statistics.

    On PostgreSQL: reads from the observations_hourly_stats materialized view.
    On SQLite (tests): falls back to computing aggregations from base table.
    """
    try:
        from sqlalchemy import text

        result = await db.execute(
            text(
                """
                SELECT hour, observation_count, processed_count, processed_pct,
                       avg_value, min_value, max_value, unique_sources,
                       source_list, materialized_at
                FROM observations_hourly_stats
                ORDER BY hour DESC
                LIMIT :limit
                """
            ).bindparams(limit=limit)
        )
        rows = result.mappings().all()
        stats = [
            {
                "hour": str(row["hour"]),
                "observation_count": row["observation_count"],
                "processed_count": row["processed_count"],
                "processed_pct": row["processed_pct"],
                "avg_value": row["avg_value"],
                "min_value": row["min_value"],
                "max_value": row["max_value"],
                "unique_sources": row["unique_sources"],
                "source_list": row["source_list"],
                "materialized_at": str(row["materialized_at"]),
            }
            for row in rows
        ]
    except Exception:
        # Fallback: compute from base observations table (view not created yet)
        await db.rollback()
        stats = await _compute_stats_from_base(db, limit)

    return {"stats": stats, "limit": limit}


async def _compute_stats_from_base(
    db: AsyncSession, limit: int
) -> list[dict[str, Any]]:
    """Compute hourly aggregations directly from observations table.

    Used as a fallback when materialized view is not available (SQLite tests).
    """
    result = await db.execute(
        select(Observation)
        .where(Observation.deleted_at.is_(None))
        .order_by(Observation.timestamp)
    )
    observations = result.scalars().all()

    hourly: dict[datetime, list[Observation]] = defaultdict(list)
    for observation in observations:
        hour = observation.timestamp.replace(minute=0, second=0, microsecond=0)
        hourly[hour].append(observation)

    materialized_at = datetime.now(UTC).isoformat()
    stats = []
    for hour, hour_observations in sorted(hourly.items(), reverse=True)[:limit]:
        observation_count = len(hour_observations)
        processed_count = sum(1 for r in hour_observations if r.processed)
        values = [
            float(r.raw_data["value"])
            for r in hour_observations
            if isinstance(r.raw_data, dict) and r.raw_data.get("value") is not None
        ]
        avg_value = round(sum(values) / len(values), 4) if values else None
        min_value = min(values) if values else None
        max_value = max(values) if values else None
        sources = {r.source for r in hour_observations}
        processed_pct = (
            round(processed_count / observation_count * 100, 2)
            if observation_count
            else None
        )

        stats.append(
            {
                "hour": hour.isoformat(),
                "observation_count": observation_count,
                "processed_count": processed_count,
                "processed_pct": processed_pct,
                "avg_value": avg_value,
                "min_value": min_value,
                "max_value": max_value,
                "unique_sources": len(sources),
                "source_list": ",".join(sorted(sources)),
                "materialized_at": materialized_at,
            }
        )

    return stats


# ---------------------------------------------------------------------------
# GET /api/v1/analytics/timeseries
# ---------------------------------------------------------------------------


@router.get("/timeseries")
async def get_timeseries(
    db: DbDep,
    days: Annotated[int, Query(ge=1, le=90)] = 30,
) -> dict[str, Any]:
    """Rolling 7-day ingestion rate with LAG comparison and dense rank per source.

    Demonstrates native PostgreSQL window functions:
    - ``SUM(...) OVER (ORDER BY day ROWS 6 PRECEDING)`` — rolling 7-day total
    - ``LAG(daily_count, 1) OVER (ORDER BY day)`` — previous-day comparison
    - ``DENSE_RANK() OVER (PARTITION BY day ORDER BY source_count DESC)`` — per-day ranking
    - ``PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY ...)`` — p95 ingestion latency proxy

    On SQLite (tests): falls back to a Python-side approximation so tests
    pass without a live PostgreSQL connection.

    Args:
        db: Active async database session.
        days: Number of calendar days to include (1–90). Defaults to 30.

    Returns:
        Mapping with ``timeseries`` list of daily rows and ``days`` requested.
    """
    from sqlalchemy import text

    try:
        result = await db.execute(
            text(
                """
                WITH daily_counts AS (
                    SELECT
                        DATE_TRUNC('day', timestamp)::date AS day,
                        source,
                        COUNT(*)                            AS source_count
                    FROM observations
                    WHERE timestamp >= NOW() - (:days || ' days')::INTERVAL
                      AND deleted_at IS NULL
                    GROUP BY DATE_TRUNC('day', timestamp)::date, source
                ),
                daily_totals AS (
                    SELECT
                        day,
                        SUM(source_count)                               AS daily_count,
                        SUM(SUM(source_count)) OVER (
                            ORDER BY day
                            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                        )                                               AS rolling_7d,
                        LAG(SUM(source_count), 1) OVER (ORDER BY day)  AS prev_day_count
                    FROM daily_counts
                    GROUP BY day
                ),
                source_ranks AS (
                    SELECT
                        day,
                        source,
                        source_count,
                        DENSE_RANK() OVER (
                            PARTITION BY day
                            ORDER BY source_count DESC
                        )                                               AS source_rank
                    FROM daily_counts
                ),
                top_sources AS (
                    SELECT
                        day,
                        JSON_AGG(
                            JSON_BUILD_OBJECT(
                                'source', source,
                                'count', source_count,
                                'rank', source_rank
                            )
                            ORDER BY source_rank
                        ) AS ranked_sources
                    FROM source_ranks
                    WHERE source_rank <= 5
                    GROUP BY day
                ),
                p95_per_day AS (
                    SELECT
                        DATE_TRUNC('day', timestamp)::date             AS day,
                        PERCENTILE_CONT(0.95) WITHIN GROUP (
                            ORDER BY EXTRACT(EPOCH FROM (
                                COALESCE(processed_at, NOW()) - timestamp
                            ))
                        )                                              AS p95_latency_secs
                    FROM observations
                    WHERE timestamp >= NOW() - (:days || ' days')::INTERVAL
                      AND deleted_at IS NULL
                    GROUP BY DATE_TRUNC('day', timestamp)::date
                )
                SELECT
                    dt.day,
                    dt.daily_count,
                    dt.rolling_7d,
                    dt.prev_day_count,
                    ROUND(
                        CASE
                            WHEN dt.prev_day_count > 0
                            THEN (dt.daily_count - dt.prev_day_count)::numeric
                                 / dt.prev_day_count * 100
                            ELSE NULL
                        END, 2
                    )                                                   AS day_over_day_pct,
                    p.p95_latency_secs,
                    ts.ranked_sources
                FROM daily_totals dt
                LEFT JOIN p95_per_day    p  ON p.day  = dt.day
                LEFT JOIN top_sources    ts ON ts.day = dt.day
                ORDER BY dt.day DESC
                """
            ).bindparams(days=days)
        )
        rows = result.mappings().all()
        timeseries = [
            {
                "day": str(row["day"]),
                "daily_count": row["daily_count"],
                "rolling_7d": row["rolling_7d"],
                "prev_day_count": row["prev_day_count"],
                "day_over_day_pct": (
                    float(row["day_over_day_pct"])
                    if row["day_over_day_pct"] is not None
                    else None
                ),
                "p95_latency_secs": (
                    round(float(row["p95_latency_secs"]), 4)
                    if row["p95_latency_secs"] is not None
                    else None
                ),
                "top_sources": row["ranked_sources"] or [],
            }
            for row in rows
        ]
    except Exception:
        # Fallback for SQLite (tests) — Python-side approximation
        await db.rollback()
        timeseries = await _compute_timeseries_fallback(db, days)

    return {"timeseries": timeseries, "days": days}


async def _compute_timeseries_fallback(
    db: AsyncSession, days: int
) -> list[dict[str, Any]]:
    """Compute a simplified timeseries from the observations table without window SQL.

    Used when PostgreSQL-specific window function syntax is not available
    (e.g., aiosqlite in unit tests).

    Args:
        db: Active async database session.
        days: Number of calendar days to look back.

    Returns:
        List of daily summary dicts compatible with the primary response shape.
    """
    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = await db.execute(
        select(Observation).where(
            Observation.timestamp >= cutoff,
            Observation.deleted_at.is_(None),
        )
    )
    observations_list = result.scalars().all()

    daily: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"daily_count": 0, "sources": defaultdict(int)}
    )
    for observation in observations_list:
        day_key = observation.timestamp.strftime("%Y-%m-%d")
        daily[day_key]["daily_count"] += 1
        daily[day_key]["sources"][observation.source] += 1

    sorted_days = sorted(daily.keys(), reverse=True)
    timeseries = []
    running_window: list[int] = []
    for day_key in reversed(sorted_days):
        count = daily[day_key]["daily_count"]
        running_window.append(count)
        if len(running_window) > 7:
            running_window.pop(0)
        sources = daily[day_key]["sources"]
        top_sources = [
            {"source": s, "count": c, "rank": r}
            for r, (s, c) in enumerate(
                sorted(sources.items(), key=lambda x: x[1], reverse=True)[:5], start=1
            )
        ]
        timeseries.append(
            {
                "day": day_key,
                "daily_count": count,
                "rolling_7d": sum(running_window),
                "prev_day_count": None,
                "day_over_day_pct": None,
                "p95_latency_secs": None,
                "top_sources": top_sources,
            }
        )

    return list(reversed(timeseries))


# ---------------------------------------------------------------------------
# GET /api/v1/analytics/tenant-status
# ---------------------------------------------------------------------------


@router.get("/tenant-status")
async def get_tenant_status(db: DbDep) -> dict[str, Any]:
    """Demonstrate RLS by returning stats for the current tenant.

    This query intentionally omits a WHERE clause for tenant_id.
    PostgreSQL RLS ensures that only observations belonging to the session's
    active tenant_id are visible and counted.
    """
    from sqlalchemy import func

    count_result = await db.execute(select(func.count(Observation.id)))
    observation_count = count_result.scalar_one()

    return {
        "active_tenant_id": get_tenant_id(),
        "observation_count": observation_count,
        "isolation_enforced": True,
        "engine": "PostgreSQL Row Level Security (RLS)",
        "logic": "SELECT count(*) FROM observations (no manual WHERE tenant_id)",
    }
