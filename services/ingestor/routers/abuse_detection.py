"""Abuse Detection API endpoints.

All routes require JWT authentication with the appropriate role:
- ``user`` / ``admin``  — listing and querying signals, summary stats
- ``user`` / ``admin``  — creating and resolving signals
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.abuse_detection import (
    AbuseSignalCreate,
    AbuseSignalListResponse,
    AbuseSignalResolve,
    AbuseSignalResponse,
    AbuseSummaryResponse,
)
from services.ingestor.auth import casbin_guard
from services.ingestor.constants import API_V1_PREFIX, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from services.ingestor.database import get_db
from services.ingestor.repositories import abuse_detection as repo


router = APIRouter(prefix=f"{API_V1_PREFIX}/abuse", tags=["abuse-detection"])

type DbDep = Annotated[AsyncSession, Depends(get_db)]

ReadJwtDep = Annotated[dict[str, Any], Depends(casbin_guard("user", "admin"))]
WriteJwtDep = Annotated[dict[str, Any], Depends(casbin_guard("user", "admin"))]


# ---------------------------------------------------------------------------
# List signals
# ---------------------------------------------------------------------------


@router.get(
    "/signals",
    response_model=AbuseSignalListResponse,
    summary="List abuse signals",
    description=(
        "Returns a paginated list of abuse signals. Supports filtering by "
        "signal type, severity, actor type, and resolved status. "
        "Tenant-admin callers must supply their ``tenant_id`` to scope results."
    ),
)
async def list_signals(
    db: DbDep,
    _claims: ReadJwtDep,
    tenant_id: int | None = Query(
        None, ge=1, description="Scope to a specific tenant."
    ),
    signal_type: str | None = Query(None, description="Filter by signal type."),
    severity: str | None = Query(None, description="low | medium | high | critical"),
    actor_type: str | None = Query(None, description="Filter by actor type."),
    resolved: bool | None = Query(
        None,
        description="True=only resolved, False=only open.",
    ),
    page: int = Query(1, ge=1, description="1-based page number."),
    page_size: int = Query(
        DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description="Results per page.",
    ),
    limit: int | None = Query(
        None,
        ge=1,
        le=MAX_PAGE_SIZE,
        description="Alias for page_size.",
    ),
    offset: int | None = Query(
        None,
        ge=0,
        description="Offset from the first observation.",
    ),
) -> AbuseSignalListResponse:
    effective_page_size = limit if limit is not None else page_size
    effective_page = (offset // effective_page_size) + 1 if offset is not None else page

    items, total = await repo.list_signals(
        db,
        tenant_id=tenant_id,
        signal_type=signal_type,
        severity=severity,
        actor_type=actor_type,
        resolved=resolved,
        page=page,
        page_size=page_size,
        limit=limit,
        offset=offset,
    )
    return AbuseSignalListResponse(
        items=items,
        total=total,
        page=effective_page,
        page_size=effective_page_size,
    )


# ---------------------------------------------------------------------------
# Create signal (manual / admin injection)
# ---------------------------------------------------------------------------


@router.post(
    "/signals",
    response_model=AbuseSignalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Manually raise an abuse signal",
    description="Admin-only endpoint to manually create an abuse signal.",
)
async def create_signal(
    db: DbDep,
    _claims: WriteJwtDep,
    payload: AbuseSignalCreate,
) -> AbuseSignalResponse:
    signal = await repo.create_signal(db, payload=payload)
    await db.commit()
    return signal


# ---------------------------------------------------------------------------
# Get single signal
# ---------------------------------------------------------------------------


@router.get(
    "/signals/{signal_id}",
    response_model=AbuseSignalResponse,
    summary="Get a single abuse signal",
)
async def get_signal(
    db: DbDep,
    _claims: ReadJwtDep,
    signal_id: int,
    tenant_id: int | None = Query(None, ge=1, description="Scope lookup to a tenant."),
) -> AbuseSignalResponse:
    signal = await repo.get_signal(db, signal_id, tenant_id=tenant_id)
    if signal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Signal not found"
        )
    return signal


# ---------------------------------------------------------------------------
# Resolve signal
# ---------------------------------------------------------------------------


@router.patch(
    "/signals/{signal_id}/resolve",
    response_model=AbuseSignalResponse,
    summary="Resolve an open abuse signal",
    description="Mark a signal as resolved. No-op if already resolved.",
)
async def resolve_signal(
    db: DbDep,
    _claims: WriteJwtDep,
    signal_id: int,
    payload: AbuseSignalResolve,
) -> AbuseSignalResponse:
    signal = await repo.resolve_signal(
        db,
        signal_id=signal_id,
        resolved_by=payload.resolved_by,
        notes=payload.notes,
    )
    if signal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signal not found or already resolved",
        )
    await db.commit()
    return signal


# ---------------------------------------------------------------------------
# Summary / dashboard stats
# ---------------------------------------------------------------------------


@router.get(
    "/summary",
    response_model=AbuseSummaryResponse,
    summary="Aggregate abuse signal stats",
    description=(
        "Returns open/resolved counts, breakdown by severity, and top actors. "
        "Optionally scoped to a tenant."
    ),
)
async def get_summary(
    db: DbDep,
    _claims: ReadJwtDep,
    tenant_id: int | None = Query(None, ge=1, description="Scope stats to a tenant."),
) -> AbuseSummaryResponse:
    return await repo.get_summary(db, tenant_id=tenant_id)
