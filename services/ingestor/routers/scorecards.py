"""API provider scorecard endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.scorecards import (
    HealthSampleCreate,
    HealthSampleResponse,
    ProviderScorecard,
    ScorecardListResponse,
)
from services.ingestor.constants import (
    API_V1_PREFIX,
    MAX_PAGE_SIZE,
    SCORECARD_DEFAULT_DAYS,
    SCORECARD_DEFAULT_LIMIT,
    SCORECARD_DEFAULT_SLO_TARGET_PCT,
    SCORECARD_MAX_DAYS,
    SCORECARD_SLO_MAX_PCT,
    SCORECARD_SLO_MIN_PCT,
)
from services.ingestor.database import get_db
from services.ingestor.repositories.scorecards import (
    get_scorecard,
    list_scorecards,
    record_health_sample,
)


router = APIRouter(prefix=f"{API_V1_PREFIX}/scorecards", tags=["scorecards"])

type DbDep = Annotated[AsyncSession, Depends(get_db)]

_R404 = {"404": {"description": "Source not found."}}
_R422 = {
    "422": {"description": "Validation error in query parameters or request body."}
}


@router.post(
    "/samples",
    response_model=HealthSampleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a provider health probe",
    responses={**_R422},
)
async def create_health_sample(
    db: DbDep,
    payload: HealthSampleCreate,
) -> HealthSampleResponse:
    """Ingest one health probe result for a provider.

    Probes are the raw data that feed scorecard computation.  Each call
    represents a single synthetic or real request made to the provider:
    its latency, whether it succeeded, and optional HTTP status and region.
    """
    return await record_health_sample(db, payload)


@router.get(
    "",
    response_model=ScorecardListResponse,
    summary="List provider scorecards",
    responses={**_R422},
)
async def get_scorecards(
    db: DbDep,
    days: Annotated[
        int,
        Query(ge=1, le=SCORECARD_MAX_DAYS, description="Look-back window in days."),
    ] = SCORECARD_DEFAULT_DAYS,
    source_id: Annotated[
        int | None, Query(ge=1, description="Filter to one source profile.")
    ] = None,
    slo_target_pct: Annotated[
        float,
        Query(
            ge=SCORECARD_SLO_MIN_PCT,
            le=SCORECARD_SLO_MAX_PCT,
            description="Uptime SLO target used for error-budget burn calculation.",
        ),
    ] = SCORECARD_DEFAULT_SLO_TARGET_PCT,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_PAGE_SIZE,
            description="Maximum number of scorecards to return.",
        ),
    ] = SCORECARD_DEFAULT_LIMIT,
) -> ScorecardListResponse:
    """Return computed scorecards for all active providers.

    Each scorecard covers the requested look-back window and includes:
    - **uptime_pct** — percentage of successful probes
    - **p95_latency_ms** — 95th-percentile response latency
    - **error_budget_burn_rate** — how fast the provider is consuming its SLO error budget
    """
    items = await list_scorecards(
        db,
        days=days,
        source_id=source_id,
        slo_target_pct=slo_target_pct,
        limit=limit,
    )
    return ScorecardListResponse(items=items, total=len(items))


@router.get(
    "/{source_id}",
    response_model=ProviderScorecard,
    summary="Get scorecard for one provider",
    responses={**_R404, **_R422},
)
async def get_provider_scorecard(
    db: DbDep,
    source_id: int,
    days: Annotated[
        int,
        Query(ge=1, le=SCORECARD_MAX_DAYS, description="Look-back window in days."),
    ] = SCORECARD_DEFAULT_DAYS,
    slo_target_pct: Annotated[
        float,
        Query(
            ge=SCORECARD_SLO_MIN_PCT,
            le=SCORECARD_SLO_MAX_PCT,
            description="Uptime SLO target used for error-budget burn calculation.",
        ),
    ] = SCORECARD_DEFAULT_SLO_TARGET_PCT,
) -> ProviderScorecard:
    """Return a detailed scorecard for a single API provider.

    Returns 404 when no active source profile with the given ID exists.
    Returns a scorecard with ``sample_count=0`` when the source exists but
    has no health samples in the requested window.
    """
    scorecard = await get_scorecard(
        db, source_id, days=days, slo_target_pct=slo_target_pct
    )
    if scorecard is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source {source_id} not found.",
        )
    return scorecard
