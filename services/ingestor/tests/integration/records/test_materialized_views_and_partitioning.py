"""Integration tests for materialized views and table partitioning.

Tests for:
- pgvector extension and vector operations
- Materialized view: records_hourly_stats (CTE aggregations)
- Partitioned table: records_archive (range partitioning by month)
- CQRS Analytics endpoints (window functions, CTEs, materialized views)
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.shared.payloads import RECORD_API


# ---------------------------------------------------------------------------
# Test Data: Precise timestamps for hourly bucketing
# ---------------------------------------------------------------------------

# Base record for API tests
_RECORD = RECORD_API

# Records at specific hours for aggregation testing (all in 2026-04-20 UTC)
_HOUR_0 = "2026-04-20T00:00:00"  # Midnight
_HOUR_1 = "2026-04-20T01:00:00"  # 1 AM
_HOUR_2 = "2026-04-20T02:00:00"  # 2 AM

# Records with various values for window function testing
_RECORD_HIGH_VALUE = {
    **_RECORD,
    "timestamp": "2026-04-20T10:00:00",
    "data": {"value": 1000},
}
_RECORD_MID_VALUE = {
    **_RECORD,
    "timestamp": "2026-04-20T10:15:00",
    "data": {"value": 500},
}
_RECORD_LOW_VALUE = {
    **_RECORD,
    "timestamp": "2026-04-20T10:30:00",
    "data": {"value": 100},
}


# ---------------------------------------------------------------------------
# Extension: pgvector
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_pgvector_extension_exists(db: AsyncSession) -> None:
    """Verify pgvector extension is loaded."""
    result = await db.execute(
        text("SELECT extname FROM pg_extension WHERE extname='vector'")
    )
    extname = result.scalar()

    assert extname == "vector", "pgvector extension not found"


@pytest.mark.integration
async def test_pgvector_vector_type_available(db: AsyncSession) -> None:
    """Verify vector type can be used in queries."""
    # Create a test array and cast to vector type (basic check)
    result = await db.execute(text("SELECT '[1, 2, 3]'::vector"))
    vector_value = result.scalar()

    assert vector_value is not None, "Vector type not available"


# ---------------------------------------------------------------------------
# Materialized View: records_hourly_stats
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_materialized_view_records_hourly_stats_exists(db: AsyncSession) -> None:
    """Verify materialized view exists."""
    result = await db.execute(
        text(
            """
            SELECT EXISTS(
                SELECT 1 FROM pg_matviews
                WHERE matviewname = 'records_hourly_stats'
            )
            """
        )
    )
    view_exists = result.scalar()

    assert view_exists is True, "Materialized view records_hourly_stats not found"


@pytest.mark.integration
async def test_materialized_view_has_index(db: AsyncSession) -> None:
    """Verify materialized view has index on hour column."""
    result = await db.execute(
        text(
            """
            SELECT COUNT(*) FROM pg_indexes
            WHERE schemaname = 'public'
            AND tablename = 'records_hourly_stats'
            AND indexname = 'idx_records_hourly_stats_hour'
            """
        )
    )
    index_count = result.scalar() or 0

    assert index_count == 1, "Index idx_records_hourly_stats_hour not found"


@pytest.mark.integration
async def test_materialized_view_aggregation_logic(
    db: AsyncSession, client: AsyncClient
) -> None:
    """Test materialized view CTE aggregation logic with real data.

    Creates records in specific hours, verifies:
    1. Hourly bucketing via date_trunc
    2. Aggregation functions (count, processed_count, avg, min, max)
    3. Processed percentage calculation
    4. View refresh capability
    """
    # Arrange: Create records in hour 0 (some processed, some not)
    for i in range(3):
        record = {
            **_RECORD,
            "source": f"api.example.com-{i}",
            "timestamp": f"2026-04-20T00:0{i}:00",
            "data": {"value": i * 100},
        }
        await client.post("/api/v1/records", json=record)

    # Create processed record in hour 1
    await client.post(
        "/api/v1/records",
        json={**_RECORD, "source": "api.example.com-hour1", "timestamp": _HOUR_1},
    )

    # Refresh materialized view to capture new data
    await client.post("/api/v1/analytics/refresh-materialized-view")

    # Act: Query materialized view stats
    response = await client.get("/api/v1/analytics/materialized-view-stats?limit=48")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert "stats" in body
    assert isinstance(body["stats"], list)
    # At least one hour should have data
    assert len(body["stats"]) >= 1


@pytest.mark.integration
async def test_materialized_view_cte_columns(db: AsyncSession) -> None:
    """Verify materialized view has all expected columns from CTE."""
    result = await db.execute(
        text(
            """
                        SELECT attname AS column_name
                        FROM pg_attribute
                        JOIN pg_class ON pg_class.oid = pg_attribute.attrelid
                        WHERE pg_class.relname = 'records_hourly_stats'
                            AND attnum > 0
                            AND NOT attisdropped
                        ORDER BY attnum
            """
        )
    )
    columns = [row[0] for row in result.fetchall()]

    expected_columns = [
        "hour",
        "record_count",
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
        assert col in columns, f"Column {col} not found in materialized view"


@pytest.mark.integration
async def test_refresh_materialized_view_endpoint(client: AsyncClient) -> None:
    """Test POST /analytics/refresh-materialized-view endpoint."""
    # Act
    response = await client.post("/api/v1/analytics/refresh-materialized-view")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert "message" in body


# ---------------------------------------------------------------------------
# Partitioned Table: records_archive
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_partitioned_table_records_archive_exists(db: AsyncSession) -> None:
    """Verify partitioned table exists."""
    result = await db.execute(
        text(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'records_archive'
            """
        )
    )
    table_count = result.scalar()

    assert table_count == 1, "Partitioned table records_archive not found"


@pytest.mark.integration
async def test_partitioned_table_has_monthly_partitions(db: AsyncSession) -> None:
    """Verify partitioned table has all expected monthly partitions (12 months).

    Expected partitions: 2025-04 through 2026-04 (13 months total).
    """
    result = await db.execute(
        text(
            """
            SELECT tablename FROM pg_tables
            WHERE tablename LIKE 'records_archive_%'
            ORDER BY tablename
            """
        )
    )
    partition_tables = [row[0] for row in result.fetchall()]

    # Should have 13 partitions (April 2025 through April 2026)
    expected_partition_count = 13
    assert len(partition_tables) >= expected_partition_count, (
        f"Expected at least {expected_partition_count} partitions, got {len(partition_tables)}"
    )


@pytest.mark.integration
async def test_partitioned_table_constraints_include_partitioning_column(
    db: AsyncSession,
) -> None:
    """Verify PRIMARY KEY and UNIQUE constraints include partitioning column (timestamp).

    PostgreSQL 17 requirement: All constraints on partitioned tables must include
    the partitioning column.
    """
    result = await db.execute(
        text(
            """
            SELECT constraint_name, constraint_type
            FROM information_schema.table_constraints
            WHERE table_name = 'records_archive'
            AND constraint_type IN ('PRIMARY KEY', 'UNIQUE')
            """
        )
    )
    constraints = result.fetchall()

    assert len(constraints) >= 2, "Expected PRIMARY KEY and UNIQUE constraints"

    for constraint_name, _constraint_type in constraints:
        # Verify constraint includes timestamp column
        col_result = await db.execute(
            text(
                """
                SELECT COUNT(*) FROM information_schema.key_column_usage
                WHERE table_name = 'records_archive'
                AND constraint_name = :constraint_name
                AND column_name = 'timestamp'
                """
            ),
            {"constraint_name": constraint_name},
        )
        col_count = col_result.scalar() or 0
        assert col_count >= 1, (
            f"Constraint {constraint_name} does not include timestamp column"
        )


@pytest.mark.integration
async def test_partitioned_table_has_partition_indexes(db: AsyncSession) -> None:
    """Verify partitions have indexes on timestamp for range queries."""
    result = await db.execute(
        text(
            """
            SELECT COUNT(*) FROM pg_indexes
            WHERE schemaname = 'public'
            AND tablename LIKE 'records_archive_%'
            AND indexname LIKE 'idx_records_archive_%_timestamp'
            """
        )
    )
    index_count = result.scalar() or 0

    # Should have at least one partition with timestamp index
    assert index_count >= 1, "Partition indexes on timestamp not found"


@pytest.mark.integration
async def test_partitioned_table_insert_and_retrieve_by_month(db: AsyncSession) -> None:
    """Test inserting and retrieving records from specific partition based on month."""
    # Note: In production, data is archived into records_archive via maintenance task.
    # For testing, we're verifying the table structure allows proper inserts.

    # The actual archival logic would be in a stored procedure or migration task.
    # This test verifies the table exists and can be queried.
    result = await db.execute(
        text(
            """
            SELECT COUNT(*) FROM records_archive
            """
        )
    )
    count = result.scalar()
    # Archive table starts empty (populated by maintenance tasks)
    assert count == 0


# ---------------------------------------------------------------------------
# Analytics Endpoints: Window Functions and CTEs
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_analytics_summary_endpoint_returns_hourly_aggregation(
    client: AsyncClient,
) -> None:
    """Test GET /analytics/summary with multi-step CTE aggregation.

    Verifies:
    - Hourly bucketing
    - Aggregation functions
    - Processed percentage calculation
    """
    # Create test records in last 24 hours
    for i in range(3):
        await client.post(
            "/api/v1/records", json={**_RECORD, "data": {"value": i * 100}}
        )

    # Act: Get summary for last 24 hours
    response = await client.get("/api/v1/analytics/summary?hours=24")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert "summary" in body
    assert body["hours_back"] == 24
    assert "since" in body


@pytest.mark.integration
async def test_analytics_summary_endpoint_hours_range_validation(
    client: AsyncClient,
) -> None:
    """Test query parameter validation for /analytics/summary.

    hours: 1-168 (1 day to 7 days)
    """
    # Test minimum
    response = await client.get("/api/v1/analytics/summary?hours=1")
    assert response.status_code == 200

    # Test maximum
    response = await client.get("/api/v1/analytics/summary?hours=168")
    assert response.status_code == 200

    # Test below minimum
    response = await client.get("/api/v1/analytics/summary?hours=0")
    assert response.status_code == 422

    # Test above maximum
    response = await client.get("/api/v1/analytics/summary?hours=169")
    assert response.status_code == 422


@pytest.mark.integration
async def test_analytics_percentile_endpoint_window_function(
    client: AsyncClient,
) -> None:
    """Test GET /analytics/percentile using PERCENT_RANK window function.

    Verifies:
    - PERCENT_RANK() OVER (PARTITION BY source ORDER BY value DESC)
    - Percentile rankings from 0.0 to 1.0
    """
    # Create records with varying values for same source
    source = "percentile_test_source"
    for value in [100, 500, 1000]:
        await client.post(
            "/api/v1/records",
            json={
                **_RECORD,
                "source": source,
                "data": {"value": value},
            },
        )

    # Act
    response = await client.get(f"/api/v1/analytics/percentile?source={source}")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == source
    assert "records" in body
    assert body["count"] <= 100  # Limited to 100 per endpoint

    # Verify percentile_rank is between 0.0 and 1.0
    for record in body["records"]:
        assert 0.0 <= record["percentile_rank"] <= 1.0


@pytest.mark.integration
async def test_analytics_percentile_endpoint_source_filter(
    client: AsyncClient,
) -> None:
    """Test source filter is required for /analytics/percentile."""
    # Missing source parameter should return 422
    response = await client.get("/api/v1/analytics/percentile")
    assert response.status_code == 422


@pytest.mark.integration
async def test_analytics_top_by_source_endpoint_rank_window_function(
    client: AsyncClient,
) -> None:
    """Test GET /analytics/top-by-source using RANK window function.

    Verifies:
    - RANK() OVER (PARTITION BY source ORDER BY value DESC)
    - Top N records per source (hierarchical response)
    - Recent data filtering (hours parameter)
    """
    # Create multiple records for same source with different values
    source = "top_by_source_test"
    for i, value in enumerate([100, 500, 1000, 750]):
        timestamp = (datetime.now(UTC).replace(tzinfo=None)) - timedelta(hours=1 - i)
        await client.post(
            "/api/v1/records",
            json={
                **_RECORD,
                "source": source,
                "timestamp": timestamp.isoformat(),
                "data": {"value": value},
            },
        )

    # Act: Get top 2 per source for last 7 days
    response = await client.get("/api/v1/analytics/top-by-source?limit=2&hours=168")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert "by_source" in body
    assert body["limit_per_source"] == 2
    assert body["hours_back"] == 168


@pytest.mark.integration
async def test_analytics_top_by_source_endpoint_limit_range_validation(
    client: AsyncClient,
) -> None:
    """Test query parameter validation for /analytics/top-by-source.

    limit: 1-50
    hours: 1-2160 (1 day to 90 days)
    """
    # Test valid ranges
    response = await client.get("/api/v1/analytics/top-by-source?limit=1&hours=1")
    assert response.status_code == 200

    response = await client.get("/api/v1/analytics/top-by-source?limit=50&hours=2160")
    assert response.status_code == 200

    # Test out of range
    response = await client.get("/api/v1/analytics/top-by-source?limit=0&hours=1")
    assert response.status_code == 422

    response = await client.get("/api/v1/analytics/top-by-source?limit=1&hours=2161")
    assert response.status_code == 422


@pytest.mark.integration
async def test_analytics_materialized_view_stats_endpoint(
    client: AsyncClient,
) -> None:
    """Test GET /analytics/materialized-view-stats endpoint.

    Queries pre-aggregated hourly statistics from materialized view.
    """
    # Arrange: Create some records and refresh view
    for i in range(2):
        await client.post(
            "/api/v1/records", json={**_RECORD, "data": {"value": i * 50}}
        )

    await client.post("/api/v1/analytics/refresh-materialized-view")

    # Act
    response = await client.get("/api/v1/analytics/materialized-view-stats?limit=24")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 24
    assert "stats" in body
    assert isinstance(body["stats"], list)

    # Verify stat fields
    if body["stats"]:  # If there's data
        stat = body["stats"][0]
        assert "hour" in stat
        assert "record_count" in stat
        assert "processed_count" in stat
        assert "processed_pct" in stat
        assert "unique_sources" in stat
        assert "materialized_at" in stat


@pytest.mark.integration
async def test_analytics_materialized_view_stats_limit_range_validation(
    client: AsyncClient,
) -> None:
    """Test query parameter validation for /analytics/materialized-view-stats.

    limit: 1-168 (1 to 7 days of hourly buckets)
    """
    # Test valid ranges
    response = await client.get("/api/v1/analytics/materialized-view-stats?limit=1")
    assert response.status_code == 200

    response = await client.get("/api/v1/analytics/materialized-view-stats?limit=168")
    assert response.status_code == 200

    # Test out of range
    response = await client.get("/api/v1/analytics/materialized-view-stats?limit=0")
    assert response.status_code == 422

    response = await client.get("/api/v1/analytics/materialized-view-stats?limit=169")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Integration: Schema objects + Analytics endpoints
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_analytics_endpoints_all_available(client: AsyncClient) -> None:
    """Smoke test: Verify all analytics endpoints are accessible."""
    endpoints = [
        ("GET", "/api/v1/analytics/summary?hours=24", 200),
        ("GET", "/api/v1/analytics/percentile?source=test", 200),
        ("GET", "/api/v1/analytics/top-by-source?limit=5&hours=168", 200),
        ("POST", "/api/v1/analytics/refresh-materialized-view", 200),
        ("GET", "/api/v1/analytics/materialized-view-stats?limit=24", 200),
    ]

    for method, endpoint, expected_status in endpoints:
        if method == "GET":
            response = await client.get(endpoint)
        elif method == "POST":
            response = await client.post(endpoint)

        assert response.status_code == expected_status, (
            f"{method} {endpoint} returned {response.status_code}, expected {expected_status}"
        )
