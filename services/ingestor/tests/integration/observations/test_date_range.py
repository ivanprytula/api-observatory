from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.observations import ObservationRequest
from services.ingestor.repositories import observations as crud


_BASE_TIME = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).replace(tzinfo=None)


@pytest.mark.integration
class TestDateRangeQueries:
    """Tests for the get_observations_by_date_range CRUD function."""

    async def test_get_observations_by_date_range_within_window(
        self, db: AsyncSession
    ) -> None:
        """Observations created within the time window are returned."""
        # Create 3 observations at different times
        t1 = _BASE_TIME
        t2 = _BASE_TIME + timedelta(hours=1)
        t3 = _BASE_TIME + timedelta(hours=2)

        await crud.create_observation(
            db, ObservationRequest(source="src-1", timestamp=t1, data={})
        )
        await crud.create_observation(
            db, ObservationRequest(source="src-2", timestamp=t2, data={})
        )
        await crud.create_observation(
            db, ObservationRequest(source="src-3", timestamp=t3, data={})
        )

        # Query range: t1 (inclusive) to t3 (exclusive)
        # Should return observations at t1 and t2
        results = await crud.get_observations_by_date_range(db, start=t1, end=t3)

        assert len(results) == 2
        assert results[0].timestamp == t2  # Ordered DESC
        assert results[1].timestamp == t1

    async def test_get_observations_by_date_range_with_source_filter(
        self, db: AsyncSession
    ) -> None:
        """Date range query respects source filter."""
        t1 = _BASE_TIME
        t2 = _BASE_TIME + timedelta(hours=1)

        await crud.create_observation(
            db, ObservationRequest(source="api-prod", timestamp=t1, data={})
        )
        await crud.create_observation(
            db, ObservationRequest(source="queue-backup", timestamp=t1, data={})
        )
        await crud.create_observation(
            db, ObservationRequest(source="api-prod", timestamp=t2, data={})
        )

        # Query for only api-prod observations in the range
        results = await crud.get_observations_by_date_range(
            db, start=t1, end=t2 + timedelta(hours=1), source="api-prod"
        )

        assert len(results) == 2
        assert all(r.source == "api-prod" for r in results), results

    async def test_get_observations_by_date_range_excludes_end_boundary(
        self, db: AsyncSession
    ) -> None:
        """Observations at the end boundary are excluded (timestamp < end)."""
        t1 = _BASE_TIME
        t2 = _BASE_TIME + timedelta(hours=1)
        t3 = _BASE_TIME + timedelta(hours=2)

        await crud.create_observation(
            db, ObservationRequest(source="src-1", timestamp=t1, data={})
        )
        await crud.create_observation(
            db, ObservationRequest(source="src-2", timestamp=t2, data={})
        )
        await crud.create_observation(
            db, ObservationRequest(source="src-3", timestamp=t3, data={})
        )

        # Query with end=t2 should exclude the t2 observation
        results = await crud.get_observations_by_date_range(db, start=t1, end=t2)

        assert len(results) == 1
        assert results[0].timestamp == t1

    async def test_get_observations_by_date_range_excludes_soft_deleted(
        self, db: AsyncSession
    ) -> None:
        """Soft-deleted observations are excluded from results."""
        t1 = _BASE_TIME

        observation1 = await crud.create_observation(
            db, ObservationRequest(source="src-1", timestamp=t1, data={})
        )
        observation2 = await crud.create_observation(
            db, ObservationRequest(source="src-2", timestamp=t1, data={})
        )

        # Soft-delete the first observation
        await crud.soft_delete_observation(db, observation1.id)

        # Query should only return the non-deleted observation
        results = await crud.get_observations_by_date_range(
            db, start=t1, end=t1 + timedelta(days=1)
        )

        assert len(results) == 1
        assert results[0].id == observation2.id

    async def test_get_observations_by_date_range_empty_result(
        self, db: AsyncSession
    ) -> None:
        """Empty result when no observations in range."""
        t1 = _BASE_TIME
        t2 = _BASE_TIME + timedelta(hours=1)

        await crud.create_observation(
            db, ObservationRequest(source="src-1", timestamp=t1, data={})
        )

        # Query range entirely after all observations
        results = await crud.get_observations_by_date_range(
            db, start=t2, end=t2 + timedelta(hours=1)
        )

        assert len(results) == 0

    async def test_get_observations_by_date_range_order_by_timestamp_desc(
        self, db: AsyncSession
    ) -> None:
        """Results are ordered by timestamp DESC (newest first)."""
        t1 = _BASE_TIME
        t2 = _BASE_TIME + timedelta(hours=1)
        t3 = _BASE_TIME + timedelta(hours=2)

        await crud.create_observation(
            db, ObservationRequest(source="src-1", timestamp=t1, data={})
        )
        await crud.create_observation(
            db, ObservationRequest(source="src-2", timestamp=t3, data={})
        )
        await crud.create_observation(
            db, ObservationRequest(source="src-3", timestamp=t2, data={})
        )

        results = await crud.get_observations_by_date_range(
            db, start=t1, end=t3 + timedelta(hours=1)
        )

        # Should be ordered DESC: t3, t2, t1
        assert len(results) == 3
        assert results[0].timestamp == t3
        assert results[1].timestamp == t2
        assert results[2].timestamp == t1
