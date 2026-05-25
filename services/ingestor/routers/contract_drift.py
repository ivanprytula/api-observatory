"""Contract snapshot and drift detection endpoints."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.contract_drift import (
    CompatibilityReportResponse,
    ContractSnapshotCreate,
    ContractSnapshotIngestResponse,
    ContractSnapshotListResponse,
    ContractSnapshotResponse,
    DriftEventListResponse,
    DriftEventResponse,
)
from services.ingestor.auth import jwt_role_guard, verify_jwt_token
from services.ingestor.constants import API_V1_PREFIX, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from services.ingestor.database import get_db
from services.ingestor.repositories.contract_drift import (
    create_contract_snapshot,
    get_compatibility_report,
    get_source_drift_events,
    get_source_snapshots,
)
from services.ingestor.repositories.source_registry import get_source_profile


logger = logging.getLogger(__name__)

router = APIRouter(prefix=f"{API_V1_PREFIX}/contracts", tags=["contract-drift"])

type DbDep = Annotated[AsyncSession, Depends(get_db)]
type JwtDep = Annotated[dict[str, Any], Depends(verify_jwt_token)]
type AdminJwtDep = Annotated[dict[str, Any], Depends(jwt_role_guard("admin"))]
# operator: data-ingest agents; admin: full access — both can ingest contract snapshots
type OperatorJwtDep = Annotated[
    dict[str, Any], Depends(jwt_role_guard("operator", "admin"))
]

_R404_SOURCE = {
    404: {
        "description": "Source profile not found.",
        "content": {"application/json": {"example": {"detail": "Source not found."}}},
    }
}


@router.post(
    "/snapshots",
    response_model=ContractSnapshotIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a schema contract snapshot",
    responses={**_R404_SOURCE},
)
async def ingest_snapshot(
    payload: ContractSnapshotCreate,
    db: DbDep,
    _: OperatorJwtDep,
) -> ContractSnapshotIngestResponse:
    """Store a schema snapshot and detect drift against the previous snapshot."""
    snapshot, drift_event = await create_contract_snapshot(db, payload)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found.",
        )

    logger.info(
        "contract_snapshot_ingested",
        extra={
            "source_id": payload.source_id,
            "snapshot_id": snapshot.id,
            "drift_event_id": drift_event.id if drift_event is not None else None,
        },
    )

    return ContractSnapshotIngestResponse(
        snapshot=ContractSnapshotResponse.model_validate(snapshot),
        drift_event=(
            DriftEventResponse.model_validate(drift_event)
            if drift_event is not None
            else None
        ),
    )


@router.get(
    "/sources/{source_id}/snapshots",
    response_model=ContractSnapshotListResponse,
    summary="List contract snapshots for a source",
    responses={**_R404_SOURCE},
)
async def list_snapshots(
    source_id: int,
    db: DbDep,
    _: JwtDep,
    offset: int = Query(0, ge=0, description="Pagination offset."),
    limit: int = Query(
        DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description="Maximum number of results to return.",
    ),
) -> ContractSnapshotListResponse:
    """Return paginated contract snapshots for a single source."""
    source = await get_source_profile(db, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found.",
        )

    snapshots, total = await get_source_snapshots(
        db,
        source_id,
        offset=offset,
        limit=limit,
    )
    return ContractSnapshotListResponse(
        items=[
            ContractSnapshotResponse.model_validate(snapshot) for snapshot in snapshots
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/sources/{source_id}/drift-events",
    response_model=DriftEventListResponse,
    summary="List drift events for a source",
    responses={**_R404_SOURCE},
)
async def list_drift_events(
    source_id: int,
    db: DbDep,
    _: JwtDep,
    offset: int = Query(0, ge=0, description="Pagination offset."),
    limit: int = Query(
        DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description="Maximum number of results to return.",
    ),
) -> DriftEventListResponse:
    """Return paginated drift events for a single source."""
    source = await get_source_profile(db, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found.",
        )

    events, total = await get_source_drift_events(
        db,
        source_id,
        offset=offset,
        limit=limit,
    )
    return DriftEventListResponse(
        items=[DriftEventResponse.model_validate(event) for event in events],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/sources/{source_id}/compatibility",
    response_model=CompatibilityReportResponse,
    summary="Get source compatibility report",
    responses={**_R404_SOURCE},
)
async def compatibility_report(
    source_id: int, db: DbDep, _: JwtDep
) -> CompatibilityReportResponse:
    """Return compatibility score and latest drift breakdown for a source."""
    source = await get_source_profile(db, source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found.",
        )

    return await get_compatibility_report(db, source_id)
