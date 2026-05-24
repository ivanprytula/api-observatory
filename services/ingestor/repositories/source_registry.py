"""Async CRUD operations for the Source Registry (SourceProfile)."""

from __future__ import annotations

import time

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.source_registry import (
    SourceHealthResponse,
    SourceProfileCreate,
    SourceProfileUpdate,
    SourceSummaryResponse,
)
from services.ingestor.constants import (
    SOURCE_HEALTH_TIMEOUT_SECONDS,
    SOURCE_HEALTH_UNHEALTHY_THRESHOLD_MS,
)
from services.ingestor.models import SourceProfile, _utcnow


async def create_source_profile(
    db: AsyncSession, payload: SourceProfileCreate
) -> SourceProfile:
    """Insert a new source profile row and return it fully hydrated.

    Args:
        db: Active async database session.
        payload: Validated create request.

    Returns:
        The persisted SourceProfile ORM instance.

    Raises:
        IntegrityError: When a profile with the same name already exists.
    """
    profile = SourceProfile(
        name=payload.name,
        url=payload.url,
        source_type=payload.source_type,
        description=payload.description,
        auth_policy=payload.auth_policy,
        quota_per_minute=payload.quota_per_minute,
        cost_per_call_usd=payload.cost_per_call_usd,
        expected_schema_version=payload.expected_schema_version,
        sla_ms=payload.sla_ms,
        tags=payload.tags,
        owner_team=payload.owner_team,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


async def get_source_profiles(
    db: AsyncSession,
    *,
    is_active: bool | None = None,
    source_type: str | None = None,
    owner_team: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> tuple[list[SourceProfile], int]:
    """Return a page of source profiles and the total matching count.

    Args:
        db: Active async database session.
        is_active: Filter by active/inactive state when given.
        source_type: Filter by protocol type when given.
        owner_team: Filter by owner team when given.
        offset: Pagination offset.
        limit: Page size.

    Returns:
        (profiles, total) tuple.
    """
    base = select(SourceProfile).where(SourceProfile.deleted_at.is_(None))
    if is_active is not None:
        base = base.where(SourceProfile.is_active == is_active)
    if source_type is not None:
        base = base.where(SourceProfile.source_type == source_type)
    if owner_team is not None:
        base = base.where(SourceProfile.owner_team == owner_team)

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    page_stmt = (
        base.order_by(SourceProfile.created_at.desc()).offset(offset).limit(limit)
    )
    rows = (await db.execute(page_stmt)).scalars().all()
    return list(rows), total


async def get_source_profile(db: AsyncSession, source_id: int) -> SourceProfile | None:
    """Fetch a single active source profile by primary key.

    Args:
        db: Active async database session.
        source_id: Primary key.

    Returns:
        SourceProfile if found and not deleted, else None.
    """
    stmt = select(SourceProfile).where(
        SourceProfile.id == source_id,
        SourceProfile.deleted_at.is_(None),
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def update_source_profile(
    db: AsyncSession, profile: SourceProfile, patch: SourceProfileUpdate
) -> SourceProfile:
    """Apply partial update to a source profile.

    Args:
        db: Active async database session.
        profile: The ORM instance to mutate.
        patch: Validated partial update payload.

    Returns:
        Updated and refreshed SourceProfile instance.
    """
    update_data = patch.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(profile, field, value)
    profile.updated_at = _utcnow()
    await db.commit()
    await db.refresh(profile)
    return profile


async def deactivate_source_profile(
    db: AsyncSession, profile: SourceProfile
) -> SourceProfile:
    """Soft-delete a source profile by setting deleted_at.

    Args:
        db: Active async database session.
        profile: The profile to deactivate.

    Returns:
        The updated ORM instance.
    """
    profile.deleted_at = _utcnow()
    profile.is_active = False
    await db.commit()
    await db.refresh(profile)
    return profile


async def get_source_summary(db: AsyncSession) -> SourceSummaryResponse:
    """Compute aggregate statistics across all source profiles.

    Args:
        db: Active async database session.

    Returns:
        SourceSummaryResponse with counts, type breakdown, and cost totals.
    """
    stmt = select(SourceProfile).where(SourceProfile.deleted_at.is_(None))
    profiles: list[SourceProfile] = list((await db.execute(stmt)).scalars().all())

    total = len(profiles)
    active = [p for p in profiles if p.is_active]
    inactive_count = total - len(active)

    sources_by_type: dict[str, int] = {}
    for p in profiles:
        sources_by_type[p.source_type] = sources_by_type.get(p.source_type, 0) + 1

    sla_values = [p.sla_ms for p in profiles if p.sla_ms is not None]
    avg_sla: float | None = sum(sla_values) / len(sla_values) if sla_values else None

    total_cost = sum(
        (p.cost_per_call_usd or 0.0) * (p.quota_per_minute or 0) for p in active
    )

    return SourceSummaryResponse(
        total_sources=total,
        active_sources=len(active),
        inactive_sources=inactive_count,
        sources_by_type=sources_by_type,
        avg_sla_ms=avg_sla,
        total_estimated_cost_per_minute_usd=total_cost,
    )


async def probe_source_health(
    db: AsyncSession, profile: SourceProfile
) -> SourceHealthResponse:
    """Perform a live HTTP HEAD/GET probe against the source URL.

    Issues a HEAD request (falls back to GET on 405) and measures round-trip
    latency. No auth headers are sent — this is a connectivity probe only.

    Args:
        db: Active async database session (unused directly, kept for consistency).
        profile: The source to probe.

    Returns:
        SourceHealthResponse with reachability, status code, and latency.
    """
    threshold = profile.sla_ms or SOURCE_HEALTH_UNHEALTHY_THRESHOLD_MS
    start = time.perf_counter()

    try:
        async with httpx.AsyncClient(
            timeout=SOURCE_HEALTH_TIMEOUT_SECONDS, follow_redirects=True
        ) as http:
            response = await http.head(profile.url)
            # Some servers reject HEAD; fall back to GET with no body read
            if response.status_code == 405:
                response = await http.get(profile.url)
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        return SourceHealthResponse(
            source_id=profile.id,
            url=profile.url,
            reachable=False,
            status_code=None,
            latency_ms=elapsed_ms,
            sla_ms=profile.sla_ms,
            sla_breach=True,
            error=str(exc),
        )

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    return SourceHealthResponse(
        source_id=profile.id,
        url=profile.url,
        reachable=True,
        status_code=response.status_code,
        latency_ms=elapsed_ms,
        sla_ms=profile.sla_ms,
        sla_breach=elapsed_ms > threshold,
        error=None,
    )
