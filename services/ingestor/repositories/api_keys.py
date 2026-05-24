"""Async CRUD operations for the ApiKey resource."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.api_keys import ApiKeyCreate
from services.ingestor.models import ApiKey, _utcnow
from services.ingestor.security.api_keys import generate_api_key


async def create_api_key(db: AsyncSession, payload: ApiKeyCreate) -> tuple[ApiKey, str]:
    """Insert a new API key row and return (orm_instance, full_raw_key).

    The ``full_raw_key`` is the value the caller must store securely; it is
    never persisted in the database.

    Args:
        db: Active async database session.
        payload: Validated create request.

    Returns:
        (ApiKey ORM instance, full_raw_key string).

    Raises:
        ValueError: If any scope in the payload is not recognised.
    """
    from services.ingestor.security.api_keys import VALID_SCOPES

    invalid = set(payload.scopes) - VALID_SCOPES
    if invalid:
        raise ValueError(f"Unknown scopes: {sorted(invalid)}")

    full_key, prefix, key_hash = generate_api_key()

    row = ApiKey(
        name=payload.name,
        key_prefix=prefix,
        key_hash=key_hash,
        tenant_id=payload.tenant_id,
        scopes=payload.scopes,
        is_active=True,
        expires_at=payload.expires_at,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row, full_key


async def get_api_key_by_prefix(db: AsyncSession, prefix: str) -> ApiKey | None:
    """Look up an ApiKey by its prefix.

    Args:
        db: Active async database session.
        prefix: The first 8 hex chars of the key.

    Returns:
        The matching ApiKey row or None.
    """
    result = await db.execute(select(ApiKey).where(ApiKey.key_prefix == prefix))
    return result.scalar_one_or_none()


async def list_api_keys(
    db: AsyncSession,
    *,
    tenant_id: int | None = None,
    is_active: bool | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[ApiKey]:
    """Return a page of API keys, optionally filtered by tenant / active state.

    Args:
        db: Active async database session.
        tenant_id: Filter to keys belonging to this tenant when given.
        is_active: Filter by active/revoked state when given.
        offset: Pagination offset.
        limit: Page size (max 100).

    Returns:
        List of matching ApiKey rows.
    """
    stmt = select(ApiKey).where(ApiKey.deleted_at.is_(None))
    if tenant_id is not None:
        stmt = stmt.where(ApiKey.tenant_id == tenant_id)
    if is_active is not None:
        stmt = stmt.where(ApiKey.is_active == is_active)
    stmt = stmt.order_by(ApiKey.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def revoke_api_key(db: AsyncSession, api_key_id: int) -> ApiKey | None:
    """Set ``is_active = False`` on the given key (soft revocation).

    Args:
        db: Active async database session.
        api_key_id: Primary key of the ApiKey to revoke.

    Returns:
        The updated ApiKey row, or None if not found.
    """
    result = await db.execute(select(ApiKey).where(ApiKey.id == api_key_id))
    row = result.scalar_one_or_none()
    if row is None:
        return None
    row.is_active = False
    row.updated_at = _utcnow()
    await db.commit()
    await db.refresh(row)
    return row
