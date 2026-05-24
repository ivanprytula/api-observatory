"""MongoDB aggregation analytics endpoints.

Exposes the two aggregation pipelines from ``storage.mongo``:

- ``GET /api/v1/mongo/ingestion-volume``  — hourly ingestion counts
- ``GET /api/v1/mongo/source-volume``     — top sources with recent docs
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from services.ingestor.storage.mongo import (
    ingestion_volume_by_hour,
    source_volume_with_recent_docs,
)


router = APIRouter(prefix="/api/v1/mongo", tags=["mongo-analytics"])

_MAX_HOURS: int = 168  # cap at 7 days
_MAX_SOURCES: int = 50
_MAX_DOCS_PER_SOURCE: int = 20


@router.get(
    "/ingestion-volume",
    summary="Hourly ingestion volume",
    response_model=list[dict[str, Any]],
)
async def get_ingestion_volume(
    source: str | None = Query(
        default=None,
        description="Filter by source name; omit to aggregate across all sources.",
        max_length=200,
    ),
    hours: int = Query(
        default=24,
        ge=1,
        le=_MAX_HOURS,
        description="Number of hourly buckets to return.",
    ),
) -> list[dict[str, Any]]:
    """Return per-hour ingestion document counts.

    Runs a MongoDB ``$group`` aggregation that truncates ``scraped_at`` to
    the hour and sums documents per bucket.

    Args:
        source: Optional source filter.
        hours: Maximum number of buckets (newest first).

    Returns:
        List of ``{"hour": "2024-01-15T10:00:00", "count": 42}`` dicts.
    """
    return await ingestion_volume_by_hour(source=source, limit_hours=hours)


@router.get(
    "/source-volume",
    summary="Top sources with recent documents",
    response_model=list[dict[str, Any]],
)
async def get_source_volume(
    top: int = Query(
        default=10,
        ge=1,
        le=_MAX_SOURCES,
        description="Number of top sources to return.",
    ),
    docs: int = Query(
        default=3,
        ge=1,
        le=_MAX_DOCS_PER_SOURCE,
        description="Recent document stubs to embed per source.",
    ),
) -> list[dict[str, Any]]:
    """Return top N sources by total document count with recent doc stubs.

    Runs a multi-stage MongoDB aggregation:
    ``$group`` ─► ``$sort`` ─► ``$limit`` ─► ``$project`` (with ``$slice``).

    Args:
        top: Maximum number of sources to include.
        docs: Number of recent document stubs to embed per source.

    Returns:
        List of ``{"source": "hn", "count": 412, "recent_docs": [...]}`` dicts.
    """
    return await source_volume_with_recent_docs(top_n_sources=top, docs_per_source=docs)
