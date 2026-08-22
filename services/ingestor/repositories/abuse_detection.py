"""Async repository for SecurityEvent persistence (abuse category).

All functions follow the project convention:
- ``db: AsyncSession`` is the **first positional** parameter
- Use SQLAlchemy 2.0 ``select()`` DSL exclusively
- Return Pydantic schema objects (not raw ORM rows) from query helpers
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.abuse_detection import (
    AbuseSeverityCount,
    AbuseSignalCreate,
    AbuseSignalResponse,
    AbuseSummaryResponse,
    AbuseTopActor,
)
from services.ingestor.models import SecurityEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_response(row: SecurityEvent) -> AbuseSignalResponse:
    return AbuseSignalResponse.model_validate(row)


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------


async def create_signal(
    db: AsyncSession,
    *,
    payload: AbuseSignalCreate,
) -> AbuseSignalResponse:
    """Persist a new SecurityEvent (category='abuse') and return the full response schema."""
    row = SecurityEvent(
        category="abuse",
        signal_type=payload.signal_type,
        actor_type=payload.actor_type,
        actor_id=payload.actor_id,
        severity=payload.severity,
        detection_rule=payload.detection_rule,
        evidence=payload.evidence,
        action_taken=payload.action_taken,
        tenant_id=payload.tenant_id,
        ip_address=payload.ip_address,
        notes=payload.notes,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return _to_response(row)


async def resolve_signal(
    db: AsyncSession,
    *,
    signal_id: int,
    resolved_by: str,
    notes: str | None = None,
) -> AbuseSignalResponse | None:
    """Mark a signal as resolved. Returns None if not found or already resolved."""
    result = await db.execute(
        select(SecurityEvent).where(
            SecurityEvent.id == signal_id,
            SecurityEvent.category == "abuse",
        )
    )
    row = result.scalar_one_or_none()
    if row is None or row.resolved_at is not None:
        return None
    row.resolved_at = datetime.now(UTC).replace(tzinfo=None)
    row.resolved_by = resolved_by
    if notes is not None:
        row.notes = notes
    await db.flush()
    await db.refresh(row)
    return _to_response(row)


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


async def get_signal(
    db: AsyncSession,
    signal_id: int,
    *,
    tenant_id: int | None = None,
) -> AbuseSignalResponse | None:
    """Return a single signal by id, optionally scoped to a tenant."""
    stmt = select(SecurityEvent).where(
        SecurityEvent.id == signal_id,
        SecurityEvent.category == "abuse",
    )
    if tenant_id is not None:
        stmt = stmt.where(SecurityEvent.tenant_id == tenant_id)
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    return _to_response(row) if row else None


async def list_signals(
    db: AsyncSession,
    *,
    tenant_id: int | None = None,
    signal_type: str | None = None,
    severity: str | None = None,
    actor_type: str | None = None,
    resolved: bool | None = None,
    page: int = 1,
    page_size: int = 50,
    offset: int | None = None,
    limit: int | None = None,
) -> tuple[list[AbuseSignalResponse], int]:
    """Return (items, total) for paginated signal listing.

    ``tenant_id`` scopes results to a specific tenant.
    ``resolved=True`` returns only resolved signals; ``resolved=False`` open only.
    """
    stmt = select(SecurityEvent).where(SecurityEvent.category == "abuse")
    if tenant_id is not None:
        stmt = stmt.where(SecurityEvent.tenant_id == tenant_id)
    if signal_type is not None:
        stmt = stmt.where(SecurityEvent.signal_type == signal_type)
    if severity is not None:
        stmt = stmt.where(SecurityEvent.severity == severity)
    if actor_type is not None:
        stmt = stmt.where(SecurityEvent.actor_type == actor_type)
    if resolved is True:
        stmt = stmt.where(SecurityEvent.resolved_at.isnot(None))
    elif resolved is False:
        stmt = stmt.where(SecurityEvent.resolved_at.is_(None))

    # Total count (before pagination)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total: int = (await db.execute(count_stmt)).scalar_one()

    # Support both page/page_size and offset/limit styles.
    effective_page_size = limit if limit is not None else page_size
    effective_offset = (
        offset if offset is not None else (page - 1) * effective_page_size
    )

    # Paginated items, newest first
    stmt = (
        stmt.order_by(SecurityEvent.created_at.desc())
        .offset(effective_offset)
        .limit(effective_page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_response(r) for r in rows], total


async def get_summary(
    db: AsyncSession,
    *,
    tenant_id: int | None = None,
) -> AbuseSummaryResponse:
    """Aggregate open/resolved counts, breakdown by severity, and top actors."""

    # Base filter
    def _base(resolved: bool):
        stmt = select(SecurityEvent).where(SecurityEvent.category == "abuse")
        if tenant_id is not None:
            stmt = stmt.where(SecurityEvent.tenant_id == tenant_id)
        if resolved:
            stmt = stmt.where(SecurityEvent.resolved_at.isnot(None))
        else:
            stmt = stmt.where(SecurityEvent.resolved_at.is_(None))
        return stmt

    # Open count
    open_count: int = (
        await db.execute(
            select(func.count()).select_from(_base(resolved=False).subquery())
        )
    ).scalar_one()

    # Resolved count
    resolved_count: int = (
        await db.execute(
            select(func.count()).select_from(_base(resolved=True).subquery())
        )
    ).scalar_one()

    # Open count by severity
    sev_stmt = (
        select(SecurityEvent.severity, func.count().label("cnt"))
        .where(
            SecurityEvent.category == "abuse",
            SecurityEvent.resolved_at.is_(None),
        )
        .group_by(SecurityEvent.severity)
    )
    if tenant_id is not None:
        sev_stmt = sev_stmt.where(SecurityEvent.tenant_id == tenant_id)
    sev_rows = (await db.execute(sev_stmt)).all()
    by_severity = [
        AbuseSeverityCount(severity=row.severity, count=row.cnt) for row in sev_rows
    ]

    # Top actors (by total signal count, unresolved only)
    actors_stmt = (
        select(
            SecurityEvent.actor_type,
            SecurityEvent.actor_id,
            func.count().label("cnt"),
            func.max(SecurityEvent.severity).label("latest_severity"),
        )
        .where(
            SecurityEvent.category == "abuse",
            SecurityEvent.resolved_at.is_(None),
        )
        .group_by(SecurityEvent.actor_type, SecurityEvent.actor_id)
        .order_by(func.count().desc())
        .limit(10)
    )
    if tenant_id is not None:
        actors_stmt = actors_stmt.where(SecurityEvent.tenant_id == tenant_id)
    actor_rows = (await db.execute(actors_stmt)).all()
    top_actors = [
        AbuseTopActor(
            actor_type=row.actor_type,
            actor_id=row.actor_id,
            signal_count=row.cnt,
            latest_severity=row.latest_severity,
        )
        for row in actor_rows
    ]

    return AbuseSummaryResponse(
        open_count=open_count,
        resolved_count=resolved_count,
        by_severity=by_severity,
        top_actors=top_actors,
    )
