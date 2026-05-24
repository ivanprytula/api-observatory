"""Integration tests for event storage with real database (Phase 1).

Tests ProcessedEvent CRUD operations, status transitions, and error handling
with actual AsyncSession against test database.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.storage.events import (
    create_processed_event,
    get_events_by_status,
    mark_event_completed,
    mark_event_failed,
    mark_event_processing,
)


@pytest.mark.integration
class TestEventsWithDB:
    """Database-backed event storage tests."""

    async def test_event_insertion(self, db: AsyncSession) -> None:
        """Insert ProcessedEvent with CRUD function."""
        event, created = await create_processed_event(
            db,
            kafka_topic="records.events",
            kafka_partition=0,
            kafka_offset=1,
            idempotency_key="insert-test-001",
            event_type="record.created",
            payload={"record_id": 1, "action": "create"},
        )
        assert created is True
        assert event.id is not None
        assert event.status == "pending"

    async def test_event_retrieval(self, db: AsyncSession) -> None:
        """Retrieve events by status."""
        # Insert test events
        await create_processed_event(
            db,
            kafka_topic="records.events",
            kafka_partition=0,
            kafka_offset=2,
            idempotency_key="retrieve-test-001",
            event_type="record.created",
            payload={"record_id": 2},
        )
        await create_processed_event(
            db,
            kafka_topic="records.events",
            kafka_partition=0,
            kafka_offset=3,
            idempotency_key="retrieve-test-002",
            event_type="record.created",
            payload={"record_id": 3},
        )

        # Retrieve pending events
        events = await get_events_by_status(db, status="pending", limit=10)
        assert len(events) >= 2
        assert all(e.status == "pending" for e in events)

    async def test_event_update_status(self, db: AsyncSession) -> None:
        """Update event status from pending → processing → completed."""
        event, _ = await create_processed_event(
            db,
            kafka_topic="records.events",
            kafka_partition=0,
            kafka_offset=4,
            idempotency_key="update-test-001",
            event_type="record.created",
            payload={"record_id": 4},
        )
        assert event.status == "pending"

        # Mark as processing
        updated = await mark_event_processing(db, event_id=event.id)
        assert updated.status == "processing"

        # Mark as completed
        completed = await mark_event_completed(db, event_id=event.id)
        assert completed.status == "completed"

    async def test_event_error_handling(self, db: AsyncSession) -> None:
        """Event can be marked as failed with error details."""
        event, _ = await create_processed_event(
            db,
            kafka_topic="records.events",
            kafka_partition=0,
            kafka_offset=5,
            idempotency_key="error-test-001",
            event_type="record.created",
            payload={"record_id": 5},
        )

        # Mark as failed
        failed = await mark_event_failed(
            db,
            event_id=event.id,
            error_message="Connection timeout after 3 retries",
            error_details={"retries": 3, "timeout_ms": 5000},
        )
        assert failed.status == "failed"
        assert failed.error_message == "Connection timeout after 3 retries"
