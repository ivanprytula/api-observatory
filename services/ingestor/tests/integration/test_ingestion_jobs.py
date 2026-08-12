"""Tests for ingestion job handlers and patterns.

Coverage:
- API single/batch ingestion
- Scheduled batch ingestion template
- Archive job template
- Idempotency tracking
- Error handling and retries
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from libs.platform.retry import IdempotencyKeyTracker
from services.ingestor.api_schemas.observations import ObservationRequest
from services.ingestor.jobs import (
    archive_old_observations,
    ingest_api_batch,
    ingest_api_single,
    ingest_scheduled_batch_example,
)
from services.ingestor.models import Observation


pytestmark = pytest.mark.integration


# ============================================================================
# IdempotencyKeyTracker Tests
# ============================================================================


class TestIdempotencyKeyTracker:
    def test_tracker_initialization(self) -> None:
        tracker = IdempotencyKeyTracker(ttl_seconds=3600)
        assert tracker.ttl_seconds == 3600
        assert len(tracker._seen) == 0

    def test_mark_seen_and_is_duplicate(self) -> None:
        tracker = IdempotencyKeyTracker()

        # First call: not seen
        assert not tracker.is_duplicate("key_1")

        # Mark as seen
        tracker.mark_seen("key_1")

        # Second call: is duplicate
        assert tracker.is_duplicate("key_1")

    def test_ttl_expiration(self) -> None:
        """Test that keys expire after TTL."""
        import time

        tracker = IdempotencyKeyTracker(ttl_seconds=1)
        tracker.mark_seen("expiring_key")

        # Should be duplicate immediately
        assert tracker.is_duplicate("expiring_key")

        # Wait for expiration
        time.sleep(1.1)

        # Should NOT be duplicate anymore (expired)
        assert not tracker.is_duplicate("expiring_key")

    def test_multiple_keys(self) -> None:
        """Test tracking multiple distinct keys."""
        tracker = IdempotencyKeyTracker()

        tracker.mark_seen("key_1")
        tracker.mark_seen("key_2")
        tracker.mark_seen("key_3")

        assert tracker.is_duplicate("key_1")
        assert tracker.is_duplicate("key_2")
        assert tracker.is_duplicate("key_3")
        assert not tracker.is_duplicate("key_4")


# ============================================================================
# API Ingestion Tests
# ============================================================================


class TestApiIngestion:
    @pytest.mark.asyncio
    async def test_ingest_api_single_success(self) -> None:
        mock_db = AsyncMock(spec=AsyncSession)

        test_observation = Observation(
            id=1,
            source="test_source",
            timestamp=datetime.now(UTC),
            raw_data={"test": "data"},
            tags=["test"],
        )

        with patch(
            "services.ingestor.jobs.crud.create_observation", new_callable=AsyncMock
        ) as mock_create:
            mock_create.return_value = test_observation

            request = ObservationRequest(
                source="test_source",
                timestamp=datetime.now(UTC),
                data={"test": "data"},
                tags=["test"],
            )

            result = await ingest_api_single(mock_db, request)

            assert result == test_observation
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_ingest_api_single_with_idempotency(self) -> None:
        """Test single observation ingestion with idempotency key."""
        mock_db = AsyncMock(spec=AsyncSession)

        with patch("services.ingestor.jobs.ingestion._dedup_tracker") as mock_tracker:
            # Simulate duplicate
            mock_tracker.is_duplicate.return_value = True

            request = ObservationRequest(
                source="test_source",
                timestamp=datetime.now(UTC),
                data={"test": "data"},
            )

            result = await ingest_api_single(
                mock_db, request, idempotency_key="dup_key"
            )

            # Should return None for duplicate
            assert result is None
            mock_tracker.is_duplicate.assert_called_once_with("dup_key")

    @pytest.mark.asyncio
    async def test_ingest_api_batch_success(self) -> None:
        """Test batch ingestion succeeds."""
        mock_db = AsyncMock(spec=AsyncSession)

        mock_observations = [
            Observation(
                id=i,
                source="test_source",
                timestamp=datetime.now(UTC),
                raw_data={"index": i},
                tags=["batch"],
            )
            for i in range(1, 4)
        ]

        with patch(
            "services.ingestor.jobs.crud.create_observations_batch",
            new_callable=AsyncMock,
        ) as mock_create:
            mock_create.return_value = mock_observations

            requests = [
                ObservationRequest(
                    source="test_source",
                    timestamp=datetime.now(UTC),
                    data={"index": i},
                    tags=["batch"],
                )
                for i in range(1, 4)
            ]

            result = await ingest_api_batch(mock_db, requests)

            assert result["inserted"] == 3
            assert result["errors"] == 0
            assert result["first_error"] is None

    @pytest.mark.asyncio
    async def test_ingest_api_batch_failure(self) -> None:
        """Test batch ingestion handles errors gracefully."""
        mock_db = AsyncMock(spec=AsyncSession)

        with patch(
            "services.ingestor.jobs.crud.create_observations_batch",
            new_callable=AsyncMock,
        ) as mock_create:
            mock_create.side_effect = ValueError("DB error")

            requests = [
                ObservationRequest(
                    source="test_source",
                    timestamp=datetime.now(UTC),
                    data={"index": i},
                )
                for i in range(1, 3)
            ]

            result = await ingest_api_batch(mock_db, requests)

            assert result["inserted"] == 0
            assert result["errors"] == 2
            assert "DB error" in result["first_error"]

    @pytest.mark.asyncio
    async def test_ingest_api_batch_duplicate_key(self) -> None:
        """Test batch ingestion skips duplicate batches."""
        mock_db = AsyncMock(spec=AsyncSession)

        with patch("services.ingestor.jobs.ingestion._dedup_tracker") as mock_tracker:
            # Simulate batch duplicate
            mock_tracker.is_duplicate.return_value = True

            requests = [
                ObservationRequest(
                    source="test_source",
                    timestamp=datetime.now(UTC),
                    data={"index": i},
                )
                for i in range(1, 3)
            ]

            result = await ingest_api_batch(
                mock_db, requests, idempotency_key_prefix="batch"
            )

            assert result["inserted"] == 0
            assert "already processed" in result["first_error"].lower()


# ============================================================================
# Scheduled Batch Ingestion Tests
# ============================================================================


class TestScheduledBatchIngestion:
    @pytest.mark.asyncio
    async def test_ingest_scheduled_batch_template(self) -> None:
        mock_db = AsyncMock(spec=AsyncSession)

        with patch(
            "services.ingestor.jobs.ingestion.ingest_api_batch", new_callable=AsyncMock
        ) as mock_ingest:
            mock_ingest.return_value = {
                "inserted": 1,
                "errors": 0,
                "first_error": None,
            }

            result = await ingest_scheduled_batch_example(mock_db)

            assert result["source"] == "example_source"
            assert result["inserted"] == 1
            assert result["errors"] == 0
            assert "duration_seconds" in result


# ============================================================================
# Archive Job Tests
# ============================================================================


class TestArchiveJob:
    @pytest.mark.asyncio
    async def test_archive_old_observations_reports_empty_dry_run(
        self,
        db: AsyncSession,
    ) -> None:
        result = await archive_old_observations(db)

        assert result["status"] == "empty"
        assert result["archived"] == 0
        assert result["deleted"] == 0
