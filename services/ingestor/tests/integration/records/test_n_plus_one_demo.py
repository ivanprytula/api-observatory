"""N+1 query demo: naive vs optimized approaches.

Demonstrates the query problem and validates both CRUD functions produce
identical results (data correctness) while showing timing differences.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.models import Record
from services.ingestor.repositories.records import (
    get_records_with_tag_counts,
    get_records_with_tag_counts_naive,
)


@pytest.mark.integration
class TestNPlusOneCRUD:
    """Test the two CRUD functions: naive (N+1) and optimized (1 query)."""

    async def test_get_records_with_tag_counts_naive_returns_correct_shape(
        self, db: AsyncSession, sample_records_with_tags: list[Record]
    ) -> None:
        """Naive function returns correct data shape."""
        if not sample_records_with_tags:
            pytest.skip("No sample records with tags created")

        result = await get_records_with_tag_counts_naive(db, limit=5)

        assert isinstance(result, list)
        assert len(result) > 0
        # Check first result has correct keys
        first = result[0]
        assert "id" in first
        assert "source" in first
        assert "timestamp" in first
        assert "tag_count" in first
        assert isinstance(first["tag_count"], int)

    async def test_get_records_with_tag_counts_optimized_returns_correct_shape(
        self, db: AsyncSession, sample_records_with_tags: list[Record]
    ) -> None:
        """Optimized function returns correct data shape."""
        if not sample_records_with_tags:
            pytest.skip("No sample records with tags created")

        result = await get_records_with_tag_counts(db, limit=5)

        assert isinstance(result, list)
        assert len(result) > 0
        # Check first result has correct keys
        first = result[0]
        assert "id" in first
        assert "source" in first
        assert "timestamp" in first
        assert "tag_count" in first
        assert isinstance(first["tag_count"], int)

    async def test_naive_and_optimized_produce_identical_tag_counts(
        self, db: AsyncSession, sample_records_with_tags: list[Record]
    ) -> None:
        """Both approaches return identical tag counts (data correctness)."""
        if not sample_records_with_tags:
            pytest.skip("No sample records with tags created")

        naive_results = await get_records_with_tag_counts_naive(db, limit=10)
        optimized_results = await get_records_with_tag_counts(db, limit=10)

        # Same number of results
        assert len(naive_results) == len(optimized_results)

        # Same tag counts in the same order (both sort DESC by ID)
        for naive, optimized in zip(naive_results, optimized_results, strict=False):
            assert naive["id"] == optimized["id"]
            assert naive["tag_count"] == optimized["tag_count"]
            assert naive["source"] == optimized["source"]

    async def test_limit_parameter_respected(
        self, db: AsyncSession, sample_records_with_tags: list[Record]
    ) -> None:
        """Both functions respect the limit parameter."""
        if not sample_records_with_tags:
            pytest.skip("No sample records with tags created")

        for limit in [1, 3, 5]:
            naive = await get_records_with_tag_counts_naive(db, limit=limit)
            optimized = await get_records_with_tag_counts(db, limit=limit)

            assert len(naive) <= limit
            assert len(optimized) <= limit
            # Both return same count at same limit
            assert len(naive) == len(optimized)

    async def test_tag_count_zero_for_empty_tags(
        self, db: AsyncSession, record_timestamp
    ) -> None:
        """Records with empty tag lists return tag_count=0."""
        from services.ingestor.api_schemas.records import RecordRequest
        from services.ingestor.repositories.records import create_record

        # Create a record with empty tags
        request = RecordRequest(
            source="test-empty-tags",
            timestamp=record_timestamp,
            data={"test": "data"},
            tags=[],
        )
        record = await create_record(db, request)

        # Query via naive
        naive_results = await get_records_with_tag_counts_naive(db, limit=1)
        naive_match = [r for r in naive_results if r["id"] == record.id]
        assert len(naive_match) == 1
        assert naive_match[0]["tag_count"] == 0

        # Query via optimized
        optimized_results = await get_records_with_tag_counts(db, limit=1)
        opt_match = [r for r in optimized_results if r["id"] == record.id]
        assert len(opt_match) == 1
        assert opt_match[0]["tag_count"] == 0

    async def test_tag_count_matches_actual_tags(
        self, db: AsyncSession, record_timestamp
    ) -> None:
        """Tag counts match the actual number of tags."""
        from services.ingestor.api_schemas.records import RecordRequest
        from services.ingestor.repositories.records import create_record

        # Create a record with 5 tags
        tags = ["tag1", "tag2", "tag3", "tag4", "tag5"]
        request = RecordRequest(
            source="test-tags",
            timestamp=record_timestamp,
            data={"test": "data"},
            tags=tags,
        )
        record = await create_record(db, request)

        # Verify tag count
        naive_results = await get_records_with_tag_counts_naive(db, limit=1)
        naive_match = [r for r in naive_results if r["id"] == record.id]
        assert naive_match[0]["tag_count"] == 5

        optimized_results = await get_records_with_tag_counts(db, limit=1)
        opt_match = [r for r in optimized_results if r["id"] == record.id]
        assert opt_match[0]["tag_count"] == 5

    async def test_excludes_soft_deleted_records(
        self, db: AsyncSession, sample_records_with_tags: list[Record]
    ) -> None:
        """Soft-deleted records are excluded from both functions."""
        from services.ingestor.repositories.records import soft_delete_record

        if not sample_records_with_tags:
            pytest.skip("No sample records with tags created")

        record_to_delete = sample_records_with_tags[0]
        await soft_delete_record(db, record_to_delete.id)

        naive_results = await get_records_with_tag_counts_naive(db, limit=100)
        optimized_results = await get_records_with_tag_counts(db, limit=100)

        # Deleted record should not appear
        naive_ids = [r["id"] for r in naive_results]
        optimized_ids = [r["id"] for r in optimized_results]

        assert record_to_delete.id not in naive_ids
        assert record_to_delete.id not in optimized_ids


@pytest.mark.integration
class TestNPlusOneEndpoint:
    """Test the GET /api/v2/records/n-plus-one-demo endpoint."""

    async def test_endpoint_returns_timing_data(
        self, client: AsyncClient, sample_records_with_tags: list[Record]
    ) -> None:
        """Endpoint returns timing comparison JSON."""
        if not sample_records_with_tags:
            pytest.skip("No sample records with tags created")

        response = await client.get("/api/v2/records/n-plus-one-demo?limit=5")

        assert response.status_code == 200
        data = response.json()

        # Check required keys
        assert "naive_ms" in data
        assert "optimized_ms" in data
        assert "speedup" in data
        assert "records_count" in data
        assert "limit" in data

        # Check types and ranges
        assert isinstance(data["naive_ms"], float)
        assert isinstance(data["optimized_ms"], float)
        assert isinstance(data["speedup"], float)
        assert isinstance(data["records_count"], int)
        assert isinstance(data["limit"], int)

        # Sanity checks
        assert data["naive_ms"] > 0
        assert data["optimized_ms"] > 0
        assert data["speedup"] > 0
        assert data["limit"] == 5

    async def test_endpoint_limit_parameter(
        self, client: AsyncClient, sample_records_with_tags: list[Record]
    ) -> None:
        """Endpoint respects limit query parameter."""
        if not sample_records_with_tags:
            pytest.skip("No sample records with tags created")

        for limit in [1, 5, 10]:
            response = await client.get(
                f"/api/v2/records/n-plus-one-demo?limit={limit}"
            )
            assert response.status_code == 200
            data = response.json()
            assert data["limit"] == limit
            assert data["records_count"] <= limit

    async def test_endpoint_default_limit(
        self, client: AsyncClient, sample_records_with_tags: list[Record]
    ) -> None:
        """Endpoint defaults limit to 10."""
        if not sample_records_with_tags:
            pytest.skip("No sample records with tags created")

        response = await client.get("/api/v2/records/n-plus-one-demo")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 10

    async def test_endpoint_validates_limit(self, client: AsyncClient) -> None:
        """Endpoint validates limit bounds (1-100)."""
        # Test limit too small
        response = await client.get("/api/v2/records/n-plus-one-demo?limit=0")
        assert response.status_code == 422  # Validation error

        # Test limit too large
        response = await client.get("/api/v2/records/n-plus-one-demo?limit=101")
        assert response.status_code == 422  # Validation error

        # Test within bounds
        response = await client.get("/api/v2/records/n-plus-one-demo?limit=50")
        assert response.status_code == 200

    async def test_speedup_naive_typically_slower_than_optimized(
        self, client: AsyncClient, sample_records_with_tags: list[Record]
    ) -> None:
        """In most cases, naive approach is slower (or equal with small data).

        Note: With 0-1 records, speeds may be similar due to DB overhead.
        With 10+ records, naive typically shows 1.5x-3x+ slower execution.
        """
        if not sample_records_with_tags:
            pytest.skip("No sample records with tags created")

        response = await client.get("/api/v2/records/n-plus-one-demo?limit=10")
        assert response.status_code == 200
        data = response.json()

        # CI timing is noisy, especially for very small datasets. Keep this as a
        # weak regression check: the naive path should not be materially faster.
        assert data["naive_ms"] >= data["optimized_ms"] * 0.7
        assert data["speedup"] >= 0.7

    async def test_endpoint_empty_database(self, client: AsyncClient) -> None:
        """Endpoint handles empty database gracefully."""
        response = await client.get("/api/v2/records/n-plus-one-demo?limit=10")
        assert response.status_code == 200
        data = response.json()

        assert data["records_count"] == 0
        assert data["limit"] == 10
        # Timing should still be populated (just fast with empty DB)
        assert data["naive_ms"] >= 0
        assert data["optimized_ms"] >= 0
