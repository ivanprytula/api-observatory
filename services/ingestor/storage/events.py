"""Event storage layer — platform-wide ProcessedEvent CRUD operations.

This module is imported by both ingestor and processor services to manage
ProcessedEvent rows (Kafka event tracking, idempotency, DLQ routing).

Industry-standard patterns:
- Idempotency via unique idempotency_key (prevent double-processing)
- Status tracking (pending → processing → completed | failed | dead_letter)
- DLQ routing (failed events sent to queue for later inspection/replay)
- Offset tracking (Kafka offset stored for replay capability)
- Error details JSON (full error context for debugging)
- Batch processing (maximize throughput with INSERT...RETURNING)
"""

import logging

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.models import ProcessedEvent, _utcnow


logger = logging.getLogger(__name__)


async def create_processed_event(
    session: AsyncSession,
    kafka_topic: str,
    kafka_partition: int,
    kafka_offset: int,
    idempotency_key: str,
    event_type: str,
    payload: dict,
) -> tuple[ProcessedEvent, bool]:
    """Create or fetch a processed event (idempotent upsert).

    Industry pattern: idempotency keys guarantee at-least-once processing
    without double-processing. If the same event arrives twice, only one
    ProcessedEvent row is created; subsequent calls return the existing row.

    Args:
        session: Active async database session.
        kafka_topic: Topic this event came from (e.g., "records.events").
        kafka_partition: Partition number.
        kafka_offset: Byte offset in the partition.
        idempotency_key: Unique key for deduplication (usually event_id or hash).
        event_type: Event type string (e.g., "record.created").
        payload: JSON event data.

    Returns:
        Tuple of (event, created):
            - event: ProcessedEvent ORM instance (new or existing).
            - created: True if new row inserted; False if already existed.
    """
    event = ProcessedEvent(
        kafka_topic=kafka_topic,
        kafka_partition=kafka_partition,
        kafka_offset=kafka_offset,
        idempotency_key=idempotency_key,
        event_type=event_type,
        payload=payload,
        status="pending",
    )

    try:
        session.add(event)
        await session.flush()
        await session.commit()
        await session.refresh(event)
        logger.info(
            "event_created",
            extra={"idempotency_key": idempotency_key, "offset": kafka_offset},
        )
        return event, True
    except IntegrityError:
        # Idempotency key already exists; fetch and return it
        await session.rollback()
        result = await session.execute(
            select(ProcessedEvent).where(
                ProcessedEvent.idempotency_key == idempotency_key
            )
        )
        existing = result.scalar_one_or_none()
        logger.info(
            "event_duplicate",
            extra={
                "idempotency_key": idempotency_key,
                "status": existing.status if existing else None,
            },
        )
        return existing, False  # ty: ignore[invalid-return-type]


async def batch_create_processed_events(
    session: AsyncSession, events: list[dict]
) -> list[ProcessedEvent]:
    """Bulk-insert events with RETURNING (single round-trip to database).

    Industry pattern: Batch processing maximizes throughput when many events
    arrive. Uses INSERT...RETURNING to avoid N+1 refresh queries.

    Args:
        session: Active async database session.
        events: List of dicts with keys: kafka_topic, kafka_partition,
            kafka_offset, idempotency_key, event_type, payload.

    Returns:
        List of fully-hydrated ProcessedEvent ORM instances.
    """
    if not events:
        return []

    stmt = insert(ProcessedEvent).values(events).returning(ProcessedEvent)
    result = await session.execute(stmt)
    processed = result.scalars().all()
    await session.commit()
    return list(processed)


async def mark_event_processing(
    session: AsyncSession, event_id: int
) -> ProcessedEvent | None:
    """Mark an event as moving from pending → processing (for retry logic).

    Increments processing_attempts counter to track how many times processed.

    Args:
        session: Active async database session.
        event_id: Primary key of the event.

    Returns:
        Updated ProcessedEvent, or None if not found.
    """
    event = await session.get(ProcessedEvent, event_id)
    if event is None:
        return None
    event.status = "processing"
    event.processing_attempts += 1
    await session.commit()
    await session.refresh(event)
    return event


async def mark_event_completed(
    session: AsyncSession, event_id: int
) -> ProcessedEvent | None:
    """Mark an event as successfully processed (pending → completed).

    Sets processed_at timestamp and status=completed.

    Args:
        session: Active async database session.
        event_id: Primary key of the event.

    Returns:
        Updated ProcessedEvent, or None if not found.
    """
    event = await session.get(ProcessedEvent, event_id)
    if event is None:
        return None
    event.status = "completed"
    event.processed_at = _utcnow()
    await session.commit()
    await session.refresh(event)
    return event


async def mark_event_failed(
    session: AsyncSession,
    event_id: int,
    error_message: str,
    error_details: dict | None = None,
) -> ProcessedEvent | None:
    """Mark an event as failed with error details for investigation.

    Industry pattern: Dead letter queue (DLQ) routing keeps failed events
    observable without breaking the normal flow.

    Args:
        session: Active async database session.
        event_id: Primary key of the event.
        error_message: Human-readable error (max 500 chars).
        error_details: Optional JSON dict with full stack/context.

    Returns:
        Updated ProcessedEvent, or None if not found.
    """
    event = await session.get(ProcessedEvent, event_id)
    if event is None:
        return None
    event.status = "failed"
    event.error_message = error_message
    event.error_details = error_details
    await session.commit()
    await session.refresh(event)
    return event


async def mark_event_dlq(
    session: AsyncSession,
    event_id: int,
    reason: str,
) -> ProcessedEvent | None:
    """Send an event to dead letter queue (permanent failure, human inspection needed).

    Dead letter queue pattern: Exhausted retries, malformed payloads, or
    downstream unavailability send events to DLQ for later replay/inspection.

    Args:
        session: Active async database session.
        event_id: Primary key of the event.
        reason: String describing why event was DLQ'd (max 500 chars).

    Returns:
        Updated ProcessedEvent, or None if not found.
    """
    event = await session.get(ProcessedEvent, event_id)
    if event is None:
        return None
    event.status = "dead_letter"
    event.dead_letter_queue = True
    event.dlq_reason = reason
    await session.commit()
    await session.refresh(event)
    return event


async def get_events_by_status(
    session: AsyncSession,
    status: str,
    limit: int = 100,
) -> list[ProcessedEvent]:
    """Fetch events by status (useful for retry loops or metrics).

    Args:
        session: Active async database session.
        status: Status to filter by (e.g., "pending", "failed", "dead_letter").
        limit: Max events to return.

    Returns:
        List of matching ProcessedEvent rows.
    """
    stmt = select(ProcessedEvent).where(ProcessedEvent.status == status).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_dlq_events(
    session: AsyncSession,
    limit: int = 100,
) -> list[ProcessedEvent]:
    """Fetch all events in the dead letter queue (for alerting/dashboards).

    Args:
        session: Active async database session.
        limit: Max events to return.

    Returns:
        List of DLQ ProcessedEvent rows.
    """
    stmt = (
        select(ProcessedEvent)
        .where(ProcessedEvent.dead_letter_queue.is_(True))
        .order_by(ProcessedEvent.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
