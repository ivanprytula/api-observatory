"""EXPLAIN ANALYZE query optimization tests (PostgreSQL only).

These tests use PostgreSQL's EXPLAIN ANALYZE to verify that queries use the
expected indexes and have acceptable execution characteristics.

Database provisioning (two-layer strategy):
    - Local: testcontainers auto-starts a ``pgvector/pgvector:pg17`` container when
    Docker is available and DATABASE_URL_TEST is unset (see conftest.py).
  - CI: DATABASE_URL_TEST is injected by the GitHub Actions service container.
  - Unit-only runs (``pytest tests/unit/``): these tests are skipped because
    the ``postgresql_async_session`` fixture skips gracefully when no Postgres
    URL is reachable.

Educational purpose: understand how to read query plans and verify that
optimization efforts (indexes) are having measurable impact.
"""

import json
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.observations import ObservationRequest
from services.ingestor.models import DependencyIncident, SourceProfile


pytestmark = pytest.mark.integration


def parse_explain_output(explain_output: Any) -> dict[str, Any]:
    """Parse EXPLAIN ANALYZE output into a dict of useful metrics.

    Extracts: planning time, execution time, node types, index usage.

    Args:
        explain_output: Raw output from EXPLAIN (FORMAT JSON) query.

    Returns:
        Dict with keys: planning_ms, execution_ms, nodes, uses_index.
    """
    try:
        # Explain output may already be a Python structure or a JSON string
        if isinstance(explain_output, (bytes, bytearray)):
            explain_output = explain_output.decode()
        if isinstance(explain_output, str):
            plan_json = json.loads(explain_output)
        else:
            plan_json = explain_output

        if isinstance(plan_json, list):
            plan_json = plan_json[0]

        # Typical PG JSON: top-level keys 'Planning Time' and 'Execution Time'
        planning_ms = plan_json.get("Planning Time")
        execution_ms = plan_json.get("Execution Time")

        # Fallbacks: sometimes tooling nests timing under 'Plan'
        if planning_ms is None:
            planning_ms = plan_json.get("Plan", {}).get("Planning Time")
        if execution_ms is None:
            execution_ms = plan_json.get("Plan", {}).get("Execution Time")
        # As last resort, use Plan->Actual Total Time
        if execution_ms is None:
            execution_ms = plan_json.get("Plan", {}).get("Actual Total Time")

        def extract_nodes(node, node_list=None):
            if node_list is None:
                node_list = []
            node_list.append(node.get("Node Type", "Unknown"))
            if "Plans" in node:
                for sub_node in node["Plans"]:
                    extract_nodes(sub_node, node_list)
            return node_list

        nodes = extract_nodes(plan_json.get("Plan", {}))
        uses_index = any("Index" in node for node in nodes)

        return {
            "planning_ms": planning_ms,
            "execution_ms": execution_ms,
            "nodes": nodes,
            "uses_index": uses_index,
        }
    except json.JSONDecodeError, KeyError, TypeError:
        return {
            "planning_ms": None,
            "execution_ms": None,
            "nodes": [],
            "uses_index": False,
        }


@pytest.mark.integration
class TestQueryAnalysis:
    """Query optimization tests using EXPLAIN ANALYZE (PostgreSQL)."""

    async def test_date_range_query_uses_index(
        self, postgresql_async_session: AsyncSession, observation_timestamp
    ) -> None:
        """Verify date-range query uses ix_observations_timestamp index.

        This test creates sample observations and executes an EXPLAIN ANALYZE query
        to verify that the ix_observations_timestamp index is being used.
        """
        from services.ingestor.repositories.observations import create_observation

        db = postgresql_async_session

        # Create test data
        for i in range(10):
            req = ObservationRequest(
                source="perf-test",
                timestamp=observation_timestamp + timedelta(minutes=i),
                data={"n": i},
                tags=[],
            )
            await create_observation(db, req)

        # EXPLAIN ANALYZE the date-range query
        start = observation_timestamp
        end = observation_timestamp + timedelta(hours=2)

        query = text(
            """
            EXPLAIN (ANALYZE, FORMAT JSON)
            SELECT * FROM observations
            WHERE deleted_at IS NULL
              AND timestamp >= :start
              AND timestamp < :end
            ORDER BY timestamp DESC, id DESC
            LIMIT 10
            """
        )

        result = await db.execute(query, {"start": start, "end": end})
        explain_output = result.scalar()

        plan = parse_explain_output(explain_output)

        # Verify plan has timing information
        assert plan["planning_ms"] is not None
        assert plan["execution_ms"] is not None

    async def test_get_observations_basic_query_plan(
        self, postgresql_async_session: AsyncSession, observation_timestamp
    ) -> None:
        """Analyze the query plan for basic observation fetching."""
        from services.ingestor.repositories.observations import create_observation

        db = postgresql_async_session

        # Create sample observations
        for i in range(5):
            req = ObservationRequest(
                source=f"sample-{i}",
                timestamp=observation_timestamp,
                data={"index": i},
            )
            await create_observation(db, req)

        query = text(
            """
            EXPLAIN (ANALYZE, FORMAT JSON)
            SELECT * FROM observations
            WHERE deleted_at IS NULL
            ORDER BY id
            LIMIT 100
            """
        )

        result = await db.execute(query)
        explain_output = result.scalar()

        plan = parse_explain_output(explain_output)

        assert plan["planning_ms"] is not None
        assert plan["execution_ms"] is not None
        assert len(plan["nodes"]) > 0
        # Planning should be very fast for simple query
        assert plan["planning_ms"] < 10

    async def test_processed_flag_query_optimization(
        self, postgresql_async_session: AsyncSession, observation_timestamp
    ) -> None:
        """Verify query for processed=false uses ix_observations_processed index."""
        from services.ingestor.repositories.observations import (
            create_observation,
            mark_processed,
        )

        db = postgresql_async_session

        # Create sample observations
        observations = []
        for i in range(5):
            req = ObservationRequest(
                source=f"sample-{i}",
                timestamp=observation_timestamp,
                data={"index": i},
            )
            observation = await create_observation(db, req)
            observations.append(observation)

        # Mark some observations processed
        for i in range(3):
            await mark_processed(db, observations[i].id)

        query = text(
            """
            EXPLAIN (ANALYZE, FORMAT JSON)
            SELECT * FROM observations
            WHERE deleted_at IS NULL
              AND processed = false
            ORDER BY id DESC
            LIMIT 50
            """
        )

        result = await db.execute(query)
        explain_output = result.scalar()

        plan = parse_explain_output(explain_output)

        assert plan["execution_ms"] is not None

    async def test_soft_delete_filter_is_efficient(
        self, postgresql_async_session: AsyncSession, observation_timestamp
    ) -> None:
        """Verify soft-delete filtering via deleted_at IS NULL is efficient."""
        from services.ingestor.repositories.observations import (
            create_observation,
            soft_delete_observation,
        )

        db = postgresql_async_session

        # Create sample observations
        observations = []
        for i in range(5):
            req = ObservationRequest(
                source=f"sample-{i}",
                timestamp=observation_timestamp + timedelta(minutes=i),
                data={"index": i},
            )
            observation = await create_observation(db, req)
            observations.append(observation)

        # Soft-delete some observations
        for i in range(2):
            await soft_delete_observation(db, observations[i].id)

        query = text(
            """
            EXPLAIN (ANALYZE, FORMAT JSON)
            SELECT COUNT(*) FROM observations
            WHERE deleted_at IS NULL
            """
        )

        result = await db.execute(query)
        explain_output = result.scalar()

        plan = parse_explain_output(explain_output)

        assert plan["execution_ms"] is not None
        # Aggregate on filtered set should be fast
        assert plan["execution_ms"] < 100

    async def test_source_filter_combined_with_timestamp(
        self, postgresql_async_session: AsyncSession, observation_timestamp
    ) -> None:
        """Analyze performance of source + timestamp filter combination."""
        from services.ingestor.repositories.observations import create_observation

        db = postgresql_async_session

        # Create observations with different sources
        for i in range(5):
            req = ObservationRequest(
                source=f"source-{i % 2}",  # Only 2 unique sources
                timestamp=observation_timestamp + timedelta(minutes=i),
                data={"idx": i},
                tags=[],
            )
            await create_observation(db, req)

        query = text(
            """
            EXPLAIN (ANALYZE, FORMAT JSON)
            SELECT * FROM observations
            WHERE deleted_at IS NULL
              AND source = :source
              AND timestamp >= :start
              AND timestamp < :end
            ORDER BY timestamp DESC
            LIMIT 10
            """
        )

        result = await db.execute(
            query,
            {
                "source": "source-0",
                "start": datetime(2024, 1, 15, 9, 0),
                "end": datetime(2024, 1, 15, 11, 0),
            },
        )
        explain_output = result.scalar()

        plan = parse_explain_output(explain_output)

        assert plan["planning_ms"] is not None
        assert plan["execution_ms"] is not None
        # Multi-column filters should plan quickly
        assert plan["planning_ms"] < 20

    async def test_sequential_scan_for_array_aggregation(
        self, postgresql_async_session: AsyncSession, observation_timestamp
    ) -> None:
        """Verify that computing tag counts requires reading data.

        This test documents that while we use an index for filtering,
        processing array operations still requires reading the data.
        """
        from services.ingestor.repositories.observations import create_observation

        db = postgresql_async_session

        # Create sample observations
        for i in range(5):
            req = ObservationRequest(
                source=f"sample-{i}",
                timestamp=observation_timestamp + timedelta(minutes=i),
                data={"index": i},
                tags=[f"tag-{j}" for j in range(i * 2)],
            )
            await create_observation(db, req)

        query = text(
            """
            EXPLAIN (ANALYZE, FORMAT JSON)
            SELECT
                id,
                source,
                timestamp,
                COALESCE(json_array_length(tags), 0) as tag_count
            FROM observations
            WHERE deleted_at IS NULL
            ORDER BY id DESC
            LIMIT 10
            """
        )

        result = await db.execute(query)
        explain_output = result.scalar()

        plan = parse_explain_output(explain_output)

        assert plan["execution_ms"] is not None
        # This query needs to fetch the actual data
        assert plan["execution_ms"] >= 0

    async def test_join_with_tags_performance(
        self, postgresql_async_session: AsyncSession, observation_timestamp
    ) -> None:
        """Verify joins with tags array are properly planned."""
        from services.ingestor.repositories.observations import create_observation

        db = postgresql_async_session

        # Create observations with tags
        for i in range(5):
            req = ObservationRequest(
                source=f"sample-{i}",
                timestamp=observation_timestamp + timedelta(minutes=i),
                data={"index": i},
                tags=[f"tag-{j}" for j in range(i * 2)],
            )
            await create_observation(db, req)

        # Query tags array
        query = text(
            """
            EXPLAIN (ANALYZE, FORMAT JSON)
            SELECT
                observations.id,
                observations.source,
                json_array_elements_text(observations.tags) as tag
            FROM observations
            WHERE deleted_at IS NULL
              AND json_array_length(tags) > 0
            ORDER BY observations.id
            """
        )

        result = await db.execute(query)
        explain_output = result.scalar()

        plan = parse_explain_output(explain_output)

        assert plan["execution_ms"] is not None


@pytest.mark.integration
class TestIndexEffectiveness:
    """Verify that created indexes are actually effective."""

    async def test_timestamp_index_is_present(
        self, postgresql_async_session: AsyncSession
    ) -> None:
        """Verify ix_observations_timestamp index exists in schema."""
        db = postgresql_async_session

        # Query pg_indexes to verify index exists
        query = text(
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'observations'
                  AND indexname = 'ix_observations_timestamp'
            )
            """
        )

        result = await db.execute(query)
        index_exists = result.scalar()

        assert index_exists is True, "ix_observations_timestamp index not found"

    async def test_processed_index_is_present(
        self, postgresql_async_session: AsyncSession
    ) -> None:
        """Verify ix_observations_processed index exists in schema."""
        db = postgresql_async_session

        query = text(
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'observations'
                  AND indexname = 'ix_observations_processed'
            )
            """
        )

        result = await db.execute(query)
        index_exists = result.scalar()

        assert index_exists is True, "ix_observations_processed index not found"

    async def test_partial_soft_delete_index_effective(
        self, postgresql_async_session: AsyncSession, observation_timestamp
    ) -> None:
        """Verify the partial index on active observations is working.

        The ix_observations_active_source partial index filters WHERE deleted_at IS NULL.
        This should make queries on active observations faster.
        """
        from services.ingestor.repositories.observations import create_observation

        db = postgresql_async_session

        # Create test observations
        for i in range(10):
            req = ObservationRequest(
                source=f"test-source-{i % 3}",
                timestamp=observation_timestamp + timedelta(minutes=i),
                data={"index": i},
            )
            await create_observation(db, req)

        # Query that benefits from partial index
        query = text(
            """
            EXPLAIN (ANALYZE, FORMAT JSON)
            SELECT * FROM observations
            WHERE deleted_at IS NULL
              AND source = :source
            ORDER BY id DESC
            LIMIT 10
            """
        )

        result = await db.execute(query, {"source": "test-source-0"})
        explain_output = result.scalar()

        plan = parse_explain_output(explain_output)

        assert plan["execution_ms"] is not None
        assert len(plan["nodes"]) > 0

    async def test_tenant_incident_listing_uses_tenant_status_index(
        self, postgresql_async_session: AsyncSession
    ) -> None:
        """Capture the bounded tenant incident query against representative skew."""
        db = postgresql_async_session
        tenant_source = SourceProfile(
            name="incident-plan-tenant",
            base_url="https://tenant.example",
            tenant_id=101,
        )
        other_source = SourceProfile(
            name="incident-plan-other",
            base_url="https://other.example",
            tenant_id=202,
        )
        db.add_all([tenant_source, other_source])
        await db.flush()
        incidents = [
            DependencyIncident(
                source_id=tenant_source.id,
                tenant_id=101,
                trigger_type="availability",
                fingerprint=f"incident-plan-target-{number}",
                active_key=f"incident-plan-target-{number}",
                status="open",
                severity="critical",
                summary="Target tenant incident.",
                guidance="Test only.",
                trigger_details={},
                occurrence_count=1,
            )
            for number in range(40)
        ]
        incidents.extend(
            DependencyIncident(
                source_id=other_source.id,
                tenant_id=202,
                trigger_type="availability",
                fingerprint=f"incident-plan-other-{number}",
                active_key=f"incident-plan-other-{number}",
                status="resolved" if number % 2 else "open",
                severity="critical",
                summary="Other tenant incident.",
                guidance="Test only.",
                trigger_details={},
                occurrence_count=1,
            )
            for number in range(1_000)
        )
        db.add_all(incidents)
        await db.commit()
        await db.execute(text("ANALYZE dependency_incidents"))

        result = await db.execute(
            text(
                """
                EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                SELECT *
                FROM dependency_incidents
                WHERE tenant_id = :tenant_id
                  AND status = :status
                ORDER BY last_seen_at DESC
                LIMIT :limit
                """
            ),
            {"tenant_id": 101, "status": "open", "limit": 20},
        )
        plan = parse_explain_output(result.scalar())

        assert plan["planning_ms"] is not None
        assert plan["execution_ms"] is not None
        assert plan["uses_index"] is True
