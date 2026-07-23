"""Schema integrity tests for Core Data Model & Migrations (Pillar 2).

Tests verify:
- All required indexes exist and are defined correctly
- Unique constraints are enforced
- Soft-delete columns present on models with TimestampMixin
- Materialized views and partitioned tables accessible
- Trigger functionality for data lifecycle

Run with: pytest tests/integration/schema/ -v
"""

from datetime import UTC

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.postgresonly
class TestObservationsTableIndexes:
    """Verify indexes on observations table are correctly defined."""

    async def test_partial_index_active_source(
        self, postgresql_async_session: AsyncSession
    ):
        """Verify partial index on (source) for active (non-deleted) observations."""
        result = await postgresql_async_session.execute(
            text("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'observations'
                  AND indexname LIKE '%active_source%'
            """)
        )
        indexes = result.fetchall()
        assert len(indexes) > 0, (
            "Partial index on (source, deleted_at IS NULL) not found"
        )

        # Verify it's a partial index (WHERE clause present)
        index_def = indexes[0][1]
        assert "WHERE" in index_def, f"Index is not partial: {index_def}"
        assert "deleted_at" in index_def, (
            f"Index does not filter deleted observations: {index_def}"
        )

    async def test_index_timestamp(self, postgresql_async_session: AsyncSession):
        """Verify index on timestamp column for range queries."""
        result = await postgresql_async_session.execute(
            text("""
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'observations'
                  AND (indexname LIKE '%timestamp%' OR indexname LIKE '%idx_observations_timestamp%')
            """)  # noqa: E501
        )
        indexes = result.fetchall()
        assert len(indexes) > 0, "Index on timestamp column not found"

    async def test_index_processed(self, postgresql_async_session: AsyncSession):
        """Verify index on processed column for filtering queries."""
        result = await postgresql_async_session.execute(
            text("""
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'observations'
                  AND (indexname LIKE '%processed%' OR indexname LIKE '%idx_observations_processed%')
            """)  # noqa: E501
        )
        indexes = result.fetchall()
        assert len(indexes) > 0, "Index on processed column not found"

    async def test_primary_key_exists(self, postgresql_async_session: AsyncSession):
        """Verify primary key on observations.id."""
        result = await postgresql_async_session.execute(
            text("""
                SELECT constraint_name FROM information_schema.table_constraints
                WHERE table_name = 'observations' AND constraint_type = 'PRIMARY KEY'
            """)
        )
        constraints = result.fetchall()
        assert len(constraints) > 0, "Primary key not found on observations table"


@pytest.mark.postgresonly
class TestObservationsTableConstraints:
    """Verify unique constraints and check constraints on observations."""

    async def test_unique_constraint_source_timestamp(
        self, postgresql_async_session: AsyncSession
    ):
        """Verify unique constraint on (source, timestamp)."""
        result = await postgresql_async_session.execute(
            text("""
                SELECT constraint_name FROM information_schema.table_constraints
                WHERE table_name = 'observations'
                  AND constraint_type = 'UNIQUE'
            """)
        )
        constraints = [row[0] for row in result.fetchall()]
        assert any("source" in c and "timestamp" in c for c in constraints), (
            f"Unique constraint on (source, timestamp) not found. Found: {constraints}"
        )

    async def test_unique_constraint_enforced(
        self, postgresql_async_session: AsyncSession
    ):
        """Verify that duplicate (source, timestamp) raises constraint violation."""
        from datetime import datetime

        now = datetime.now(UTC).replace(tzinfo=None)

        # Insert first observation
        await postgresql_async_session.execute(
            text("""
                INSERT INTO observations (source, timestamp, raw_data, tags, processed, created_at)
                VALUES (:source, :timestamp, :raw_data, :tags, :processed, :created_at)
            """),
            {
                "source": "test-unique-source",
                "timestamp": now,
                "raw_data": '{"value": 1}',
                "tags": "[]",
                "processed": False,
                "created_at": now,
            },
        )
        await postgresql_async_session.commit()

        # Attempt duplicate insert (should fail)
        with pytest.raises(Exception) as exc_info:  # IntegrityError
            await postgresql_async_session.execute(
                text("""
                    INSERT INTO observations (source, timestamp, raw_data, tags, processed, created_at)
                    VALUES (:source, :timestamp, :raw_data, :tags, :processed, :created_at)
                """),  # noqa: E501
                {
                    "source": "test-unique-source",
                    "timestamp": now,
                    "raw_data": '{"value": 2}',
                    "tags": "[]",
                    "processed": False,
                    "created_at": now,
                },
            )
            await postgresql_async_session.commit()

        assert "unique" in str(exc_info.value).lower(), (
            f"Expected unique constraint violation, got: {exc_info.value}"
        )


@pytest.mark.postgresonly
class TestProcessedEventsTableIndexes:
    """Verify indexes on processed_events table."""

    async def test_index_idempotency_key(self, postgresql_async_session: AsyncSession):
        """Verify unique index on idempotency_key."""
        result = await postgresql_async_session.execute(
            text("""
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'processed_events'
                  AND (indexname LIKE '%idempotency_key%'
                       OR indexname LIKE '%ix_events_idempotency_key%')
            """)
        )
        indexes = result.fetchall()
        assert len(indexes) > 0, "Index on idempotency_key not found"

    async def test_index_status(self, postgresql_async_session: AsyncSession):
        """Verify index on status column for filtering."""
        result = await postgresql_async_session.execute(
            text("""
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'processed_events'
                  AND (indexname LIKE '%status%' OR indexname LIKE '%ix_events_status%')
            """)
        )
        indexes = result.fetchall()
        assert len(indexes) > 0, "Index on status column not found"

    async def test_index_kafka_offset(self, postgresql_async_session: AsyncSession):
        """Verify index on kafka_offset for offset tracking."""
        result = await postgresql_async_session.execute(
            text("""
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'processed_events'
                  AND (indexname LIKE '%kafka_offset%' OR indexname LIKE '%ix_events_kafka_offset%')
            """)
        )
        indexes = result.fetchall()
        assert len(indexes) > 0, "Index on kafka_offset not found"


@pytest.mark.postgresonly
class TestProcessedEventsConstraints:
    """Verify constraints on processed_events."""

    async def test_unique_index_idempotency_enforced(
        self, postgresql_async_session: AsyncSession
    ):
        """Verify that duplicate idempotency_key raises constraint violation."""
        from datetime import datetime

        now = datetime.now(UTC).replace(tzinfo=None)

        # Insert first event
        await postgresql_async_session.execute(
            text("""
                INSERT INTO processed_events (
                  kafka_topic, kafka_partition, kafka_offset, idempotency_key,
                                 event_type, payload, status, processing_attempts,
                                 dead_letter_queue, created_at
                ) VALUES (
                  :kafka_topic, :kafka_partition, :kafka_offset, :idempotency_key,
                                 :event_type, :payload, :status, :processing_attempts,
                                 :dead_letter_queue, :created_at
                )
            """),
            {
                "kafka_topic": "test-topic",
                "dead_letter_queue": False,
                "kafka_partition": 0,
                "kafka_offset": 100,
                "idempotency_key": "unique-key-123",
                "event_type": "test.event",
                "payload": "{}",
                "status": "pending",
                "processing_attempts": 0,
                "created_at": now,
            },
        )
        await postgresql_async_session.commit()

        # Attempt duplicate idempotency_key (should fail)
        with pytest.raises(Exception) as exc_info:
            await postgresql_async_session.execute(
                text("""
                    INSERT INTO processed_events (
                      kafka_topic, kafka_partition, kafka_offset, idempotency_key,
                                         event_type, payload, status, processing_attempts,
                                         dead_letter_queue, created_at
                    ) VALUES (
                      :kafka_topic, :kafka_partition, :kafka_offset, :idempotency_key,
                                         :event_type, :payload, :status, :processing_attempts,
                                         :dead_letter_queue, :created_at
                    )
                """),
                {
                    "kafka_topic": "another-topic",
                    "kafka_partition": 1,
                    "kafka_offset": 200,
                    "idempotency_key": "unique-key-123",  # Duplicate
                    "event_type": "test.event",
                    "payload": "{}",
                    "status": "pending",
                    "processing_attempts": 0,
                    "dead_letter_queue": False,
                    "created_at": now,
                },
            )
            await postgresql_async_session.commit()

        assert "unique" in str(exc_info.value).lower(), (
            f"Expected unique constraint on idempotency_key, got: {exc_info.value}"
        )


@pytest.mark.postgresonly
class TestMaterializedViews:
    """Verify materialized views exist and are queryable."""

    async def test_observations_hourly_stats_view_exists(
        self, postgresql_async_session: AsyncSession
    ):
        """Verify observations_hourly_stats materialized view exists."""
        result = await postgresql_async_session.execute(
            text("""
                SELECT EXISTS(
                  SELECT 1 FROM pg_matviews
                  WHERE matviewname = 'observations_hourly_stats'
                )
            """)
        )
        exists = result.scalar()
        assert exists, "Materialized view observations_hourly_stats not found"

    async def test_observations_hourly_stats_queryable(
        self, postgresql_async_session: AsyncSession
    ):
        """Verify observations_hourly_stats can be queried."""
        result = await postgresql_async_session.execute(
            text("SELECT COUNT(*) FROM observations_hourly_stats")
        )
        count = result.scalar()
        assert count is not None, "Failed to query observations_hourly_stats"

    async def test_observations_hourly_stats_columns(
        self, postgresql_async_session: AsyncSession
    ):
        """Verify observations_hourly_stats has expected columns."""
        result = await postgresql_async_session.execute(
            text("""
                SELECT a.attname AS column_name
                FROM pg_attribute AS a
                JOIN pg_class AS c ON a.attrelid = c.oid
                WHERE c.relname = 'observations_hourly_stats'
                  AND c.relkind = 'm'
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                ORDER BY a.attnum
            """)
        )
        columns = [row[0] for row in result.fetchall()]
        expected_columns = [
            "hour",
            "observation_count",
            "processed_count",
            "processed_pct",
            "avg_value",
            "min_value",
            "max_value",
            "unique_sources",
            "source_list",
            "materialized_at",
        ]
        for col in expected_columns:
            assert col in columns, (
                f"Expected column '{col}' not found in observations_hourly_stats"
            )


@pytest.mark.postgresonly
class TestObservationArchive:
    """Verify the Phase 3A relational observation archive exists."""

    async def test_observations_archive_table_exists(
        self, postgresql_async_session: AsyncSession
    ):
        """Verify observations_archive partitioned table exists."""
        result = await postgresql_async_session.execute(
            text("""
                SELECT EXISTS(
                  SELECT 1 FROM information_schema.tables
                  WHERE table_name = 'observations_archive'
                )
            """)
        )
        exists = result.scalar()
        assert exists, "Archive table observations_archive not found"

    async def test_observations_archive_has_retention_columns(
        self, postgresql_async_session: AsyncSession
    ):
        """Verify the archive preserves lifecycle and retention metadata."""
        result = await postgresql_async_session.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'observations_archive'
            """)
        )
        columns = {row[0] for row in result.fetchall()}
        assert {"id", "timestamp", "deleted_at", "archived_at"} <= columns


@pytest.mark.postgresonly
class TestSoftDeleteColumns:
    """Verify soft-delete columns present on all expected tables."""

    async def test_observations_has_soft_delete_columns(
        self, postgresql_async_session: AsyncSession
    ):
        """Verify observations table has created_at, updated_at, deleted_at."""
        result = await postgresql_async_session.execute(
            text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'observations'
                ORDER BY column_name
            """)
        )
        columns = [row[0] for row in result.fetchall()]
        expected = ["created_at", "updated_at", "deleted_at"]
        for col in expected:
            assert col in columns, (
                f"Soft-delete column '{col}' not found on observations"
            )

    async def test_processed_events_has_soft_delete_columns(
        self, postgresql_async_session: AsyncSession
    ):
        """Verify processed_events table has created_at, updated_at, deleted_at."""
        result = await postgresql_async_session.execute(
            text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'processed_events'
                ORDER BY column_name
            """)
        )
        columns = [row[0] for row in result.fetchall()]
        expected = ["created_at", "updated_at", "deleted_at"]
        for col in expected:
            assert col in columns, (
                f"Soft-delete column '{col}' not found on processed_events"
            )


@pytest.mark.postgresonly
class TestExtensions:
    """Verify required PostgreSQL extensions are installed."""

    async def test_pgvector_extension(self, postgresql_async_session: AsyncSession):
        """Verify pgvector extension is installed."""
        result = await postgresql_async_session.execute(
            text("""
                SELECT EXISTS(
                  SELECT 1 FROM pg_extension
                  WHERE extname = 'vector'
                )
            """)
        )
        exists = result.scalar()
        assert exists, "pgvector extension not installed"


@pytest.mark.postgresonly
class TestOutboxInboxSchema:
    """Verify outbox/inbox baseline schema and idempotency constraints."""

    async def test_outbox_inbox_tables_exist(
        self, postgresql_async_session: AsyncSession
    ) -> None:
        """Verify outbox_events and inbox_consumptions tables are present."""
        result = await postgresql_async_session.execute(
            text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN ('outbox_events', 'inbox_consumptions')
            """)
        )
        table_names = {row[0] for row in result.fetchall()}
        assert "outbox_events" in table_names, "outbox_events table not found"
        assert "inbox_consumptions" in table_names, "inbox_consumptions table not found"

    async def test_outbox_idempotency_unique_constraint_enforced(
        self, postgresql_async_session: AsyncSession
    ) -> None:
        """Verify duplicate outbox idempotency_key is rejected."""
        from datetime import datetime

        now = datetime.now(UTC).replace(tzinfo=None)

        await postgresql_async_session.execute(
            text("""
                INSERT INTO outbox_events (
                  aggregate_type, aggregate_id, event_type, payload,
                  idempotency_key, publish_attempts, created_at, updated_at
                )
                VALUES (
                  :aggregate_type, :aggregate_id, :event_type, :payload,
                  :idempotency_key, :publish_attempts, :created_at, :updated_at
                )
            """),
            {
                "aggregate_type": "observation",
                "aggregate_id": "observation-1",
                "event_type": "observation.created",
                "payload": '{"observation_id": 1}',
                "idempotency_key": "outbox-uniq-1",
                "publish_attempts": 0,
                "created_at": now,
                "updated_at": now,
            },
        )
        await postgresql_async_session.commit()

        with pytest.raises(Exception) as exc_info:
            await postgresql_async_session.execute(
                text("""
                    INSERT INTO outbox_events (
                      aggregate_type, aggregate_id, event_type, payload,
                      idempotency_key, publish_attempts, created_at, updated_at
                    )
                    VALUES (
                      :aggregate_type, :aggregate_id, :event_type, :payload,
                      :idempotency_key, :publish_attempts, :created_at, :updated_at
                    )
                """),
                {
                    "aggregate_type": "observation",
                    "aggregate_id": "observation-2",
                    "event_type": "observation.updated",
                    "payload": '{"observation_id": 2}',
                    "idempotency_key": "outbox-uniq-1",
                    "publish_attempts": 0,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            await postgresql_async_session.commit()

        assert "unique" in str(exc_info.value).lower(), (
            f"Expected outbox idempotency unique violation, got: {exc_info.value}"
        )

    async def test_inbox_consumer_message_unique_constraint_enforced(
        self, postgresql_async_session: AsyncSession
    ) -> None:
        """Verify duplicate (consumer_name, message_id) is rejected."""
        from datetime import datetime

        now = datetime.now(UTC).replace(tzinfo=None)

        await postgresql_async_session.execute(
            text("""
                INSERT INTO inbox_consumptions (
                  consumer_name, message_id, event_type, payload,
                  processed_at, created_at, updated_at
                )
                VALUES (
                  :consumer_name, :message_id, :event_type, :payload,
                  :processed_at, :created_at, :updated_at
                )
            """),
            {
                "consumer_name": "analytics-projection",
                "message_id": "msg-unique-1",
                "event_type": "observation.created",
                "payload": '{"observation_id": 1}',
                "processed_at": now,
                "created_at": now,
                "updated_at": now,
            },
        )
        await postgresql_async_session.commit()

        with pytest.raises(Exception) as exc_info:
            await postgresql_async_session.execute(
                text("""
                    INSERT INTO inbox_consumptions (
                      consumer_name, message_id, event_type, payload,
                      processed_at, created_at, updated_at
                    )
                    VALUES (
                      :consumer_name, :message_id, :event_type, :payload,
                      :processed_at, :created_at, :updated_at
                    )
                """),
                {
                    "consumer_name": "analytics-projection",
                    "message_id": "msg-unique-1",
                    "event_type": "observation.created",
                    "payload": '{"observation_id": 2}',
                    "processed_at": now,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            await postgresql_async_session.commit()

        assert "unique" in str(exc_info.value).lower(), (
            f"Expected inbox unique violation, got: {exc_info.value}"
        )
