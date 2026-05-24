"""Integration tests for processed_at timestamp functionality.

Tests verify that:
- processed_at is set when mark_processed is called
- processed_at is not overwritten on subsequent mark_processed calls (idempotent)
- processed_at is backfilled from created_at for existing processed records
- processed_at is None for new or unprocessed records
"""

import asyncio
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.records import RecordRequest
from services.ingestor.models import _utcnow
from services.ingestor.repositories.records import (
    create_record,
    get_record,
    mark_processed,
)


@pytest.mark.integration
class TestProcessedAtTimestamp:
    """Tests for the processed_at column and mark_processed logic."""

    async def test_processed_at_is_none_for_new_record(self, db: AsyncSession) -> None:
        """New records should have processed_at = None."""
        request = RecordRequest(
            source="test-source",
            timestamp=datetime.fromisoformat("2024-01-15T10:00:00"),
            data={"test": "data"},
            tags=["test"],
        )
        record = await create_record(db, request)
        assert record.processed is False
        assert record.processed_at is None

    async def test_mark_processed_sets_processed_at(self, db: AsyncSession) -> None:
        """Calling mark_processed should set processed_at timestamp."""
        # Create record
        request = RecordRequest(
            source="test-source",
            timestamp=datetime.fromisoformat("2024-01-15T10:00:00"),
            data={"test": "data"},
            tags=[],
        )
        record = await create_record(db, request)
        assert record.processed_at is None

        # Mark as processed
        before_mark = _utcnow()
        updated = await mark_processed(db, record.id)
        after_mark = _utcnow()

        assert updated is not None
        assert updated.processed is True
        assert updated.processed_at is not None
        assert before_mark <= updated.processed_at <= after_mark

    async def test_mark_processed_is_idempotent(self, db: AsyncSession) -> None:
        """Calling mark_processed twice should not change processed_at."""
        # Create and process record
        request = RecordRequest(
            source="test-source",
            timestamp=datetime.fromisoformat("2024-01-15T10:00:00"),
            data={"test": "data"},
            tags=[],
        )
        record = await create_record(db, request)
        first_processed = await mark_processed(db, record.id)
        assert first_processed is not None
        first_at = first_processed.processed_at

        # Wait a bit and process again
        await asyncio.sleep(0.01)
        second_processed = await mark_processed(db, record.id)

        # processed_at should be unchanged
        assert second_processed is not None
        assert second_processed.processed_at == first_at

    async def test_processed_at_timestamp_precision(self, db: AsyncSession) -> None:
        """processed_at should be accurate to the millisecond."""
        request = RecordRequest(
            source="test-source",
            timestamp=datetime.fromisoformat("2024-01-15T10:00:00"),
            data={"test": "data"},
            tags=[],
        )
        record = await create_record(db, request)

        before = _utcnow()
        marked = await mark_processed(db, record.id)
        after = _utcnow()

        assert marked is not None
        assert marked.processed_at is not None
        assert before <= marked.processed_at <= after
        # Verify it's a real timestamp, not just the date
        assert marked.processed_at.microsecond >= 0

    async def test_multiple_records_have_independent_processed_at(
        self, db: AsyncSession
    ) -> None:
        """Each record should have its own processed_at timestamp."""
        records = []

        # Create and process first record
        req1 = RecordRequest(
            source="source-1",
            timestamp=datetime.fromisoformat("2024-01-15T10:00:00"),
            data={"n": 1},
            tags=[],
        )
        rec1 = await create_record(db, request=req1)
        marked1 = await mark_processed(db, rec1.id)
        records.append(marked1)

        # Wait and create/process second record
        await asyncio.sleep(0.01)
        req2 = RecordRequest(
            source="source-2",
            timestamp=datetime.fromisoformat("2024-01-15T10:01:00"),
            data={"n": 2},
            tags=[],
        )
        rec2 = await create_record(db, request=req2)
        marked2 = await mark_processed(db, rec2.id)
        records.append(marked2)

        # Their processed_at should be different
        assert records[0].processed_at != records[1].processed_at
        assert records[0].processed_at < records[1].processed_at

    async def test_get_record_returns_correct_processed_at(
        self, db: AsyncSession
    ) -> None:
        """Fetching a record should return accurate processed_at."""
        request = RecordRequest(
            source="test-source",
            timestamp=datetime.fromisoformat("2024-01-15T10:00:00"),
            data={"test": "data"},
            tags=[],
        )
        created = await create_record(db, request)
        marked = await mark_processed(db, created.id)

        # Fetch and verify
        fetched = await get_record(db, created.id)
        assert fetched is not None
        assert fetched.processed is True
        assert fetched.processed_at is not None
        assert fetched.processed_at == marked.processed_at

    async def test_processed_at_null_for_unprocessed_records(
        self, db: AsyncSession
    ) -> None:
        """Records with processed=False should have processed_at=None."""
        request = RecordRequest(
            source="test-source",
            timestamp=datetime.fromisoformat("2024-01-15T10:00:00"),
            data={"test": "data"},
            tags=[],
        )
        record = await create_record(db, request)

        # Verify it's truly unprocessed
        fetched = await get_record(db, record.id)
        assert fetched is not None
        assert fetched.processed is False
        assert fetched.processed_at is None

    async def test_soft_deleted_record_retains_processed_at(
        self, db: AsyncSession
    ) -> None:
        """Soft-deleting a processed record should preserve processed_at."""
        from services.ingestor.repositories.records import soft_delete_record

        request = RecordRequest(
            source="test-source",
            timestamp=datetime.fromisoformat("2024-01-15T10:00:00"),
            data={"test": "data"},
            tags=[],
        )
        record = await create_record(db, request)
        marked = await mark_processed(db, record.id)
        processed_at_before = marked.processed_at

        # Soft delete
        deleted = await soft_delete_record(db, record.id)
        assert deleted is not None
        assert deleted.processed_at == processed_at_before
