"""Source Registry router — CRUD + health probe + summary endpoints."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.source_registry import (
    SourceHealthResponse,
    SourceProfileCreate,
    SourceProfileListResponse,
    SourceProfileResponse,
    SourceProfileUpdate,
    SourceSummaryResponse,
)
from services.ingestor.constants import (
    API_V1_PREFIX,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    SOURCE_PROFILE_TYPE_MAX,
)
from services.ingestor.database import get_db
from services.ingestor.repositories.source_registry import (
    create_source_profile,
    deactivate_source_profile,
    get_source_profile,
    get_source_profiles,
    get_source_summary,
    probe_source_health,
    update_source_profile,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix=f"{API_V1_PREFIX}/sources", tags=["source-registry"])

type DbDep = Annotated[AsyncSession, Depends(get_db)]

# ---------------------------------------------------------------------------
# Shared error-response docs
# ---------------------------------------------------------------------------
_R404 = {
    404: {
        "description": "Source profile not found.",
        "content": {"application/json": {"example": {"detail": "Source not found."}}},
    }
}
_R409 = {
    409: {
        "description": "A source with that name already exists.",
        "content": {
            "application/json": {
                "example": {"detail": "Source name already registered."}
            }
        },
    }
}
_R422 = {
    422: {
        "description": "Request validation failed.",
        "content": {
            "application/json": {"example": {"detail": "Field validation error."}}
        },
    }
}


# ---------------------------------------------------------------------------
# POST /api/v1/sources — register a source
# ---------------------------------------------------------------------------
@router.post(
    "",
    response_model=SourceProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a source profile",
    responses={**_R409, **_R422},
)
async def register_source(
    payload: SourceProfileCreate, db: DbDep
) -> SourceProfileResponse:
    """Register a new external data source in the registry.

    The name must be unique. Returns the created profile including its assigned `id`.
    Secrets (API keys, tokens) are never stored here — `auth_policy` stores
    metadata only (header name, auth type).
    """
    try:
        profile = await create_source_profile(db, payload)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Source name already registered.",
        ) from None

    logger.info(
        "source_registered", extra={"source_id": profile.id, "name": profile.name}
    )
    return SourceProfileResponse.model_validate(profile)


# ---------------------------------------------------------------------------
# GET /api/v1/sources — list sources
# ---------------------------------------------------------------------------
@router.get(
    "",
    response_model=SourceProfileListResponse,
    summary="List source profiles",
    responses={**_R422},
)
async def list_sources(
    db: DbDep,
    is_active: bool | None = Query(None, description="Filter by active state."),
    source_type: str | None = Query(
        None,
        max_length=SOURCE_PROFILE_TYPE_MAX,
        description="Filter by source type (rest, webhook, file, graphql, grpc).",
    ),
    owner_team: str | None = Query(None, description="Filter by owner team."),
    offset: int = Query(0, ge=0, description="Pagination offset."),
    limit: int = Query(
        DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description="Maximum number of results to return.",
    ),
) -> SourceProfileListResponse:
    """Return a paginated list of source profiles.

    All filter parameters are optional and may be combined.
    """
    profiles, total = await get_source_profiles(
        db,
        is_active=is_active,
        source_type=source_type,
        owner_team=owner_team,
        offset=offset,
        limit=limit,
    )
    return SourceProfileListResponse(
        items=[SourceProfileResponse.model_validate(p) for p in profiles],
        total=total,
        offset=offset,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/sources/summary — aggregate statistics
# Note: this route MUST appear before /{source_id} to avoid path shadowing.
# ---------------------------------------------------------------------------
@router.get(
    "/summary",
    response_model=SourceSummaryResponse,
    summary="Aggregate source registry statistics",
)
async def source_summary(db: DbDep) -> SourceSummaryResponse:
    """Return aggregate counts, type breakdown, and cost estimates.

    Useful for dashboards and capacity-planning views.
    """
    return await get_source_summary(db)


# ---------------------------------------------------------------------------
# GET /api/v1/sources/{source_id} — get one profile
# ---------------------------------------------------------------------------
@router.get(
    "/{source_id}",
    response_model=SourceProfileResponse,
    summary="Get a source profile by ID",
    responses={**_R404},
)
async def get_source(source_id: int, db: DbDep) -> SourceProfileResponse:
    """Fetch a single source profile."""
    profile = await get_source_profile(db, source_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Source not found."
        )
    return SourceProfileResponse.model_validate(profile)


# ---------------------------------------------------------------------------
# PATCH /api/v1/sources/{source_id} — partial update
# ---------------------------------------------------------------------------
@router.patch(
    "/{source_id}",
    response_model=SourceProfileResponse,
    summary="Update a source profile",
    responses={**_R404, **_R422},
)
async def patch_source(
    source_id: int, patch: SourceProfileUpdate, db: DbDep
) -> SourceProfileResponse:
    """Partially update a source profile.

    Only fields present in the request body are changed. Omit a field to leave it unchanged.
    """
    profile = await get_source_profile(db, source_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Source not found."
        )

    updated = await update_source_profile(db, profile, patch)
    logger.info("source_updated", extra={"source_id": source_id})
    return SourceProfileResponse.model_validate(updated)


# ---------------------------------------------------------------------------
# DELETE /api/v1/sources/{source_id} — soft delete
# ---------------------------------------------------------------------------
@router.delete(
    "/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate (soft-delete) a source profile",
    responses={**_R404},
)
async def delete_source(source_id: int, db: DbDep) -> None:
    """Mark a source profile as deleted.

    The row is retained for audit purposes; it will no longer appear in list
    or health-probe endpoints.
    """
    profile = await get_source_profile(db, source_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Source not found."
        )

    await deactivate_source_profile(db, profile)
    logger.info("source_deactivated", extra={"source_id": source_id})


# ---------------------------------------------------------------------------
# GET /api/v1/sources/{source_id}/health — live probe
# ---------------------------------------------------------------------------
@router.get(
    "/{source_id}/health",
    response_model=SourceHealthResponse,
    summary="Probe source reachability and latency",
    responses={**_R404},
)
async def source_health(source_id: int, db: DbDep) -> SourceHealthResponse:
    """Perform a live HEAD (or GET) request against the source URL.

    Returns reachability, HTTP status code, and measured round-trip latency.
    The `sla_breach` flag is set when latency exceeds the profile's `sla_ms`
    target (or 5 000 ms if unset).

    > **Note**: This endpoint makes a real outbound network call. Use sparingly
    > in automated tests to avoid rate-limiting the target source.
    """
    profile = await get_source_profile(db, source_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Source not found."
        )

    return await probe_source_health(db, profile)
