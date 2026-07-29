"""Outbox/Inbox repository helpers for reliable event delivery patterns."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.models import InboxConsumption, OutboxEvent, _utcnow


async def add_outbox_event(
    db: AsyncSession,
    *,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    payload: dict,
    idempotency_key: str,
    tenant_id: int | None = None,
) -> OutboxEvent:
    """Add an idempotent outbox row without committing the caller's transaction."""
    statement = (
        insert(OutboxEvent)
        .values(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            idempotency_key=idempotency_key,
            tenant_id=tenant_id,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(OutboxEvent)
    )
    event = await db.scalar(statement)
    if event is not None:
        return event

    existing = await db.scalar(
        select(OutboxEvent).where(OutboxEvent.idempotency_key == idempotency_key)
    )
    if existing is None:
        raise RuntimeError(
            "Outbox idempotency conflict did not return an existing row."
        )
    return existing


async def enqueue_outbox_event(
    db: AsyncSession,
    *,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    payload: dict,
    idempotency_key: str,
    tenant_id: int | None = None,
) -> OutboxEvent:
    """Compatibility wrapper that persists and commits one outbox event."""
    event = await add_outbox_event(
        db,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload,
        idempotency_key=idempotency_key,
        tenant_id=tenant_id,
    )
    await db.commit()
    await db.refresh(event)
    return event


async def list_pending_outbox_events(
    db: AsyncSession,
    *,
    limit: int = 100,
) -> list[OutboxEvent]:
    """Return unpublished outbox events in deterministic order."""
    stmt = (
        select(OutboxEvent)
        .where(
            OutboxEvent.published_at.is_(None),
            OutboxEvent.deleted_at.is_(None),
        )
        .order_by(OutboxEvent.id)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def claim_pending_outbox_events(
    db: AsyncSession,
    *,
    limit: int = 100,
    claim_token: str | None = None,
    lease_seconds: int = 30,
    now: datetime | None = None,
) -> list[OutboxEvent]:
    """Atomically claim unpublished outbox rows for one publisher worker.

    Uses SELECT FOR UPDATE SKIP LOCKED so multiple workers can safely process
    outbox rows without duplicate claims.
    """
    current_time = now or _utcnow()
    token = claim_token or str(uuid4())
    stmt = (
        select(OutboxEvent)
        .where(
            OutboxEvent.published_at.is_(None),
            OutboxEvent.deleted_at.is_(None),
            or_(
                OutboxEvent.next_attempt_at.is_(None),
                OutboxEvent.next_attempt_at <= current_time,
            ),
            or_(
                OutboxEvent.lease_expires_at.is_(None),
                OutboxEvent.lease_expires_at <= current_time,
            ),
        )
        .order_by(OutboxEvent.id)
        .with_for_update(skip_locked=True)
        .limit(limit)
    )
    result = await db.execute(stmt)
    events = list(result.scalars().all())

    for event in events:
        event.publish_attempts += 1
        event.claim_token = token
        event.lease_expires_at = current_time + timedelta(seconds=lease_seconds)

    await db.commit()
    return events


async def mark_outbox_published(
    db: AsyncSession,
    *,
    event_id: int,
    published_at: datetime | None = None,
    claim_token: str | None = None,
) -> OutboxEvent | None:
    """Mark one outbox event as published."""
    stmt = select(OutboxEvent).where(OutboxEvent.id == event_id)
    if claim_token is not None:
        stmt = stmt.where(OutboxEvent.claim_token == claim_token)
    event = await db.scalar(stmt)
    if event is None:
        return None

    event.published_at = published_at or _utcnow()
    event.last_error = None
    event.next_attempt_at = None
    event.lease_expires_at = None
    event.claim_token = None

    await db.commit()
    await db.refresh(event)
    return event


async def mark_outbox_publish_failed(
    db: AsyncSession,
    *,
    event_id: int,
    error_message: str,
    next_attempt_at: datetime | None = None,
    claim_token: str | None = None,
) -> OutboxEvent | None:
    """Observation a publish failure while keeping the row pending for retry."""
    stmt = select(OutboxEvent).where(OutboxEvent.id == event_id)
    if claim_token is not None:
        stmt = stmt.where(OutboxEvent.claim_token == claim_token)
    event = await db.scalar(stmt)
    if event is None:
        return None

    event.last_error = error_message[:512]
    event.published_at = None
    event.next_attempt_at = next_attempt_at
    event.lease_expires_at = None
    event.claim_token = None

    await db.commit()
    await db.refresh(event)
    return event


async def try_observation_inbox_consumption(
    db: AsyncSession,
    *,
    consumer_name: str,
    message_id: str,
    event_type: str,
    payload: dict,
) -> bool:
    """Observation inbox processing once; return False when already consumed.

    Uses a unique constraint on (consumer_name, message_id) to guarantee
    idempotent consumer behavior under concurrency.
    """
    row = InboxConsumption(
        consumer_name=consumer_name,
        message_id=message_id,
        event_type=event_type,
        payload=payload,
        status="completed",
        processed_at=_utcnow(),
    )
    db.add(row)

    try:
        await db.commit()
        return True
    except IntegrityError:
        await db.rollback()
        return False
