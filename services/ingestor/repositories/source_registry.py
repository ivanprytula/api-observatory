"""Async CRUD operations for the Source Registry (SourceProfile)."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from urllib.parse import urlsplit

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


def _is_forbidden_ip(ip_value: str) -> bool:
    """Return True when an IP points to non-public network space."""
    addr = ipaddress.ip_address(ip_value)
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


async def validate_source_base_url(base_url: str, *, allow_http: bool = False) -> None:
    """Validate base URL scheme and resolved IPs to prevent SSRF."""
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"https", "http"}:
        raise ValueError("base_url must use https scheme.")
    if parsed.scheme == "http" and not allow_http:
        raise ValueError("base_url must use https scheme.")
    if parsed.hostname is None:
        raise ValueError("base_url must include a valid hostname.")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(
            parsed.hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror:
        raise ValueError("base_url hostname could not be resolved.") from None

    resolved_ips = {info[4][0] for info in infos if info[4]}

    if not resolved_ips:
        raise ValueError("base_url hostname could not be resolved.")

    forbidden = sorted(ip for ip in resolved_ips if _is_forbidden_ip(ip))
    if forbidden:
        raise ValueError("base_url resolves to private or local IP space.")


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
        base_url=str(payload.base_url),
        health_check_path=payload.health_check_path,
        probe_interval_seconds=payload.probe_interval_seconds,
        is_active=payload.is_active,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


async def get_source_profiles(
    db: AsyncSession,
    *,
    is_active: bool | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[SourceProfile], int]:
    """Return a page of source profiles and the total matching count.

    Args:
        db: Active async database session.
        is_active: Filter by active/inactive state when given.
        offset: Pagination offset.
        limit: Page size.

    Returns:
        (profiles, total) tuple.
    """
    base = select(SourceProfile).where(SourceProfile.deleted_at.is_(None))
    if is_active is not None:
        base = base.where(SourceProfile.is_active == is_active)

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    page_stmt = (
        base.order_by(SourceProfile.created_at.desc()).offset(offset).limit(limit)
    )
    rows = (await db.execute(page_stmt)).scalars().all()
    return list(rows), total


async def get_source_profile(
    db: AsyncSession, source_id: int, *, include_deleted: bool = False
) -> SourceProfile | None:
    """Fetch a single active source profile by primary key.

    Args:
        db: Active async database session.
        source_id: Primary key.

    Returns:
        SourceProfile if found and not deleted, else None.
    """
    stmt = select(SourceProfile).where(SourceProfile.id == source_id)
    if not include_deleted:
        stmt = stmt.where(SourceProfile.deleted_at.is_(None))
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
    if profile.deleted_at is None:
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

    intervals = [p.probe_interval_seconds for p in profiles]
    avg_probe_interval = sum(intervals) / len(intervals) if intervals else None

    return SourceSummaryResponse(
        total_sources=total,
        active_sources=len(active),
        inactive_sources=inactive_count,
        avg_probe_interval_seconds=avg_probe_interval,
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
    target_url = (
        f"{profile.base_url.rstrip('/')}/{profile.health_check_path.lstrip('/')}"
    )
    threshold = SOURCE_HEALTH_UNHEALTHY_THRESHOLD_MS
    start = time.perf_counter()

    try:
        async with httpx.AsyncClient(
            timeout=SOURCE_HEALTH_TIMEOUT_SECONDS, follow_redirects=False
        ) as http:
            response = await http.head(target_url)
            # Some servers reject HEAD; fall back to GET with no body read
            if response.status_code == 405:
                response = await http.get(target_url)
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        return SourceHealthResponse(
            source_id=profile.id,
            target_url=target_url,
            reachable=False,
            status_code=None,
            latency_ms=elapsed_ms,
            sla_breach=True,
            error=str(exc),
        )

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    return SourceHealthResponse(
        source_id=profile.id,
        target_url=target_url,
        reachable=True,
        status_code=response.status_code,
        latency_ms=elapsed_ms,
        sla_breach=elapsed_ms > threshold,
        error=None,
    )
