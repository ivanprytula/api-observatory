"""Tenant-safe dependency incident lifecycle endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.incidents import (
    DependencyIncidentListResponse,
    DependencyIncidentResponse,
)
from services.ingestor.constants import API_V1_PREFIX, MAX_PAGE_SIZE
from services.ingestor.core.auth import (
    casbin_guard,
    get_casbin_enforcer,
    verify_jwt_token,
)
from services.ingestor.core.database import get_db
from services.ingestor.metrics import dependency_incident_transitions_total
from services.ingestor.repositories.incidents import (
    acknowledge_incident,
    get_incident,
    list_incidents,
    resolve_incident,
)


router = APIRouter(prefix=f"{API_V1_PREFIX}/incidents", tags=["incidents"])

type DbDep = Annotated[AsyncSession, Depends(get_db)]
type JwtDep = Annotated[dict[str, Any], Depends(verify_jwt_token)]
type OperatorJwtDep = Annotated[dict[str, Any], Depends(casbin_guard("user", "admin"))]


def _roles(claims: dict[str, Any]) -> set[str]:
    sub = claims.get("sub") or ""
    tenant_id = claims.get("tenant_id")
    domain = str(tenant_id) if tenant_id is not None else "*"
    enforcer = get_casbin_enforcer()
    return set(enforcer.get_roles_for_user_in_domain(sub, domain))


def _scope(claims: dict[str, Any]) -> tuple[int | None, bool]:
    admin = "admin" in _roles(claims)
    raw_tenant_id = claims.get("tenant_id")
    tenant_id = int(raw_tenant_id) if raw_tenant_id is not None else None
    if not admin and tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A tenant-scoped identity is required.",
        )
    return tenant_id, admin


def _actor(claims: dict[str, Any]) -> str:
    return str(claims.get("sub") or "unknown")


@router.get("", response_model=DependencyIncidentListResponse)
async def get_incidents(
    db: DbDep,
    claims: JwtDep,
    incident_status: Annotated[
        str | None,
        Query(alias="status", pattern="^(open|acknowledged|resolved)$"),
    ] = None,
    source_id: Annotated[int | None, Query(ge=1)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
) -> DependencyIncidentListResponse:
    tenant_id, admin = _scope(claims)
    incidents, total = await list_incidents(
        db,
        tenant_id=tenant_id,
        admin=admin,
        status=incident_status,
        source_id=source_id,
        offset=offset,
        limit=limit,
    )
    return DependencyIncidentListResponse(
        items=[DependencyIncidentResponse.model_validate(item) for item in incidents],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/{incident_id}", response_model=DependencyIncidentResponse)
async def get_incident_by_id(
    incident_id: int, db: DbDep, claims: JwtDep
) -> DependencyIncidentResponse:
    tenant_id, admin = _scope(claims)
    incident = await get_incident(db, incident_id, tenant_id=tenant_id, admin=admin)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    return DependencyIncidentResponse.model_validate(incident)


@router.post("/{incident_id}/acknowledge", response_model=DependencyIncidentResponse)
async def acknowledge_incident_by_id(
    incident_id: int, db: DbDep, claims: OperatorJwtDep
) -> DependencyIncidentResponse:
    tenant_id, admin = _scope(claims)
    incident = await get_incident(db, incident_id, tenant_id=tenant_id, admin=admin)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    try:
        await acknowledge_incident(incident, actor=_actor(claims))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    await db.commit()
    await db.refresh(incident)
    dependency_incident_transitions_total.labels(
        trigger_type=incident.trigger_type, transition="acknowledged"
    ).inc()
    return DependencyIncidentResponse.model_validate(incident)


@router.post("/{incident_id}/resolve", response_model=DependencyIncidentResponse)
async def resolve_incident_by_id(
    incident_id: int, db: DbDep, claims: OperatorJwtDep
) -> DependencyIncidentResponse:
    tenant_id, admin = _scope(claims)
    incident = await get_incident(db, incident_id, tenant_id=tenant_id, admin=admin)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    try:
        await resolve_incident(incident, actor=_actor(claims))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    await db.commit()
    await db.refresh(incident)
    dependency_incident_transitions_total.labels(
        trigger_type=incident.trigger_type, transition="resolved"
    ).inc()
    return DependencyIncidentResponse.model_validate(incident)
