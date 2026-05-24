"""Insight Engine endpoints for anomalies, trends, and recommendations."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.insights import (
    AnomalyFeedResponse,
    RecommendationFeedResponse,
    TrendFeedResponse,
)
from services.ingestor.constants import API_V1_PREFIX, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from services.ingestor.database import get_db
from services.ingestor.repositories.insights import (
    get_anomaly_insights,
    get_recommendation_insights,
    get_trend_insights,
)


router = APIRouter(prefix=f"{API_V1_PREFIX}/insights", tags=["insights"])

type DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get(
    "/anomalies",
    response_model=AnomalyFeedResponse,
    summary="Get anomaly insight feed",
)
async def anomaly_feed(
    db: DbDep,
    source_id: int | None = Query(
        None,
        ge=1,
        description="Optional source filter.",
    ),
    limit: int = Query(
        DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description="Maximum number of anomalies to return.",
    ),
) -> AnomalyFeedResponse:
    """Return anomaly insights generated from recent drift events."""
    items = await get_anomaly_insights(db, limit=limit, source_id=source_id)
    return AnomalyFeedResponse(items=items, total=len(items))


@router.get(
    "/trends",
    response_model=TrendFeedResponse,
    summary="Get trend insight feed",
)
async def trend_feed(
    db: DbDep,
    limit: int = Query(
        DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description="Maximum number of trend insights to return.",
    ),
) -> TrendFeedResponse:
    """Return trend insights generated from compatibility deltas."""
    items = await get_trend_insights(db, limit=limit)
    return TrendFeedResponse(items=items, total=len(items))


@router.get(
    "/recommendations",
    response_model=RecommendationFeedResponse,
    summary="Get recommendation insight feed",
)
async def recommendation_feed(
    db: DbDep,
    source_id: int | None = Query(
        None,
        ge=1,
        description="Optional source filter.",
    ),
    limit: int = Query(
        DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description="Maximum number of recommendations to return.",
    ),
) -> RecommendationFeedResponse:
    """Return recommendations generated from recent anomalies."""
    items = await get_recommendation_insights(db, limit=limit, source_id=source_id)
    return RecommendationFeedResponse(items=items, total=len(items))
