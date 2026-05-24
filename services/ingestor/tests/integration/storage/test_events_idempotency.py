"""Integration tests for event storage idempotency (Phase 1).

Tests the idempotency guarantee: same idempotency_key always returns the same
event ID, regardless of how many times the operation is retried.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.models import ProcessedEvent
from services.ingestor.storage.events import (
    create_processed_event,
    mark_event_failed,
)


@pytest.mark.integration
async def test_event_idempotency(db: AsyncSession) -> None:
    """Same idempotency_key twice → second insert returns existing event."""
    idempotency_key = "test-key-12345"

    # First insert
    event1, created1 = await create_processed_event(
        db,
        kafka_topic="records.events",
        kafka_partition=0,
        kafka_offset=100,
        idempotency_key=idempotency_key,
        event_type="record.created",
        payload={"record_id": 1},
    )
    assert created1 is True
    assert event1.idempotency_key == idempotency_key
    assert event1.status == "pending"

    # Second insert with same key should return existing event
    event2, created2 = await create_processed_event(
        db,
        kafka_topic="records.events",
        kafka_partition=0,
        kafka_offset=101,
        idempotency_key=idempotency_key,
        event_type="record.created",
        payload={"record_id": 1},
    )
    assert created2 is False
    assert event2.id == event1.id  # Same event ID


@pytest.mark.integration
async def test_event_idempotency_with_different_data(db: AsyncSession) -> None:
    """Same idempotency_key with different offset → returns existing (ignores new)."""
    idempotency_key = "test-key-5678"

    # First insert
    event1, created1 = await create_processed_event(
        db,
        kafka_topic="records.events",
        kafka_partition=0,
        kafka_offset=200,
        idempotency_key=idempotency_key,
        event_type="record.created",
        payload={"record_id": 1},
    )
    original_payload = event1.payload
    original_offset = event1.kafka_offset

    # Try to insert with different offset (simulates retry)
    event2, created2 = await create_processed_event(
        db,
        kafka_topic="records.events",
        kafka_partition=0,
        kafka_offset=999,  # Different offset (retry scenario)
        idempotency_key=idempotency_key,
        event_type="record.created",
        payload={"record_id": 1},
    )

    # Same event ID, original offset preserved (idempotency win)
    assert created2 is False
    assert event2.id == event1.id
    assert event2.payload == original_payload
    assert event2.kafka_offset == original_offset


@pytest.mark.integration
async def test_event_idempotency_with_failure(db: AsyncSession) -> None:
    """Event can transition through status lifecycle (pending → failed)."""
    idempotency_key = "test-key-failed"

    # Create event
    event, created = await create_processed_event(
        db,
        kafka_topic="records.events",
        kafka_partition=0,
        kafka_offset=300,
        idempotency_key=idempotency_key,
        event_type="record.created",
        payload={"record_id": 1},
    )
    assert created is True
    assert event.status == "pending"

    # Mark as failed
    await mark_event_failed(
        db,
        event_id=event.id,
        error_message="Database connection lost",
        error_details={"retries": 3, "last_error": "timeout"},
    )

    # Fetch and verify state persisted
    stmt = select(ProcessedEvent).where(ProcessedEvent.id == event.id)
    result = await db.execute(stmt)
    fetched = result.scalar_one()
    assert fetched.status == "failed"
    assert fetched.error_message == "Database connection lost"
    assert fetched.error_details == {"retries": 3, "last_error": "timeout"}
