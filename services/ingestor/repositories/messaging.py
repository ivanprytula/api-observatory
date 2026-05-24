"""Outbox/Inbox repository helpers for reliable event delivery patterns."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.models import InboxConsumption, OutboxEvent, _utcnow


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
    """Persist a domain event in the transactional outbox."""
    event = OutboxEvent(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload,
        idempotency_key=idempotency_key,
        tenant_id=tenant_id,
    )
    db.add(event)
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
) -> list[OutboxEvent]:
    """Atomically claim unpublished outbox rows for one publisher worker.

    Uses SELECT FOR UPDATE SKIP LOCKED so multiple workers can safely process
    outbox rows without duplicate claims.
    """
    stmt = (
        select(OutboxEvent)
        .where(
            OutboxEvent.published_at.is_(None),
            OutboxEvent.deleted_at.is_(None),
        )
        .order_by(OutboxEvent.id)
        .with_for_update(skip_locked=True)
        .limit(limit)
    )
    result = await db.execute(stmt)
    events = list(result.scalars().all())

    for event in events:
        event.publish_attempts += 1

    await db.commit()
    return events


async def mark_outbox_published(
    db: AsyncSession,
    *,
    event_id: int,
    published_at: datetime | None = None,
) -> OutboxEvent | None:
    """Mark one outbox event as published."""
    stmt = select(OutboxEvent).where(OutboxEvent.id == event_id)
    event = await db.scalar(stmt)
    if event is None:
        return None

    event.published_at = published_at or _utcnow()
    event.last_error = None

    await db.commit()
    await db.refresh(event)
    return event


async def mark_outbox_publish_failed(
    db: AsyncSession,
    *,
    event_id: int,
    error_message: str,
) -> OutboxEvent | None:
    """Record a publish failure while keeping the row pending for retry."""
    stmt = select(OutboxEvent).where(OutboxEvent.id == event_id)
    event = await db.scalar(stmt)
    if event is None:
        return None

    event.last_error = error_message[:512]
    event.published_at = None

    await db.commit()
    await db.refresh(event)
    return event


async def try_record_inbox_consumption(
    db: AsyncSession,
    *,
    consumer_name: str,
    message_id: str,
    event_type: str,
    payload: dict,
) -> bool:
    """Record inbox processing once; return False when already consumed.

    Uses a unique constraint on (consumer_name, message_id) to guarantee
    idempotent consumer behavior under concurrency.
    """
    row = InboxConsumption(
        consumer_name=consumer_name,
        message_id=message_id,
        event_type=event_type,
        payload=payload,
    )
    db.add(row)

    try:
        await db.commit()
        return True
    except IntegrityError:
        await db.rollback()
        return False
