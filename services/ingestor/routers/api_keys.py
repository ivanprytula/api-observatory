"""API key management endpoints.

Endpoints:
- POST   /api/v1/api-keys         — create a new scoped API key (returns full key once)
- GET    /api/v1/api-keys         — list keys (filter by tenant / active state)
- DELETE /api/v1/api-keys/{id}    — revoke a key (soft delete)
- GET    /api/v1/api-keys/scopes  — list all valid scope tokens

All mutating endpoints require the ``admin`` scope (or are intentionally
public in test scenarios where auth is disabled).
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.api_keys import (
    ApiKeyCreate,
    ApiKeyCreatedResponse,
    ApiKeyResponse,
)
from services.ingestor.database import get_db
from services.ingestor.repositories.api_keys import (
    create_api_key,
    list_api_keys,
    revoke_api_key,
)
from services.ingestor.security.api_keys import VALID_SCOPES


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/api-keys", tags=["api-keys"])

type DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.post(
    "",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API key",
    description=(
        "Generates a tenant-scoped API key with explicit permission scopes. "
        "The ``full_key`` field in the response is shown **once** — store it securely."
    ),
)
async def create_key(payload: ApiKeyCreate, db: DbDep) -> ApiKeyCreatedResponse:
    """Create a new API key and return the full raw key (shown once)."""
    try:
        row, full_key = await create_api_key(db, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from None

    logger.info(
        "api_key_created",
        extra={"api_key_id": row.id, "tenant_id": row.tenant_id, "name": row.name},
    )
    return ApiKeyCreatedResponse(
        id=row.id,
        name=row.name,
        key_prefix=row.key_prefix,
        tenant_id=row.tenant_id,
        scopes=row.scopes,
        is_active=row.is_active,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        full_key=full_key,
    )


@router.get(
    "",
    response_model=list[ApiKeyResponse],
    summary="List API keys",
)
async def get_keys(
    db: DbDep,
    tenant_id: int | None = Query(None, description="Filter by tenant ID."),
    is_active: bool | None = Query(None, description="Filter by active state."),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> list[ApiKeyResponse]:
    """Return a paginated list of API keys."""
    rows = await list_api_keys(
        db, tenant_id=tenant_id, is_active=is_active, offset=offset, limit=limit
    )
    return [ApiKeyResponse.model_validate(r) for r in rows]


@router.delete(
    "/{api_key_id}",
    response_model=ApiKeyResponse,
    summary="Revoke an API key",
    description="Soft-revokes a key by setting ``is_active = false``. Cannot be undone via API.",
)
async def revoke_key(api_key_id: int, db: DbDep) -> ApiKeyResponse:
    """Revoke (disable) an API key by ID."""
    row = await revoke_api_key(db, api_key_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key {api_key_id} not found",
        )
    logger.info("api_key_revoked", extra={"api_key_id": api_key_id})
    return ApiKeyResponse.model_validate(row)


@router.get(
    "/scopes",
    response_model=list[str],
    summary="List valid permission scopes",
)
async def list_scopes() -> list[str]:
    """Return all recognised scope tokens that can be assigned to API keys."""
    return sorted(VALID_SCOPES)
