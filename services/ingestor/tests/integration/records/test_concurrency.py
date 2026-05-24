"""Integration tests for concurrent operations (Steps 8–9, Phase 2).

Tests asyncio.gather concurrency patterns:
  - TestAsyncGather: N concurrent enrich requests all succeed
  - TestRaceConditionHandling: concurrent upserts with race condition demo

Pattern: asyncio.gather fires requests in parallel, simulating real-world
load on the pipeline. Enrich tests work on any DB (aiosqlite or PostgreSQL).
Upsert race tests may skip on SQLite due to session isolation limitations.
"""

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.records import RecordRequest
from tests.shared.payloads import RECORD_API


_BASE_PAYLOAD = {
    **RECORD_API,
    "source": "concurrency-test",
    "timestamp": "2024-06-01T12:00:00",
}


# ---------------------------------------------------------------------------
# TestAsyncGather: Concurrent Enrich Requests
# ---------------------------------------------------------------------------
@pytest.mark.integration
class TestAsyncGather:
    """Test asyncio.gather concurrency for enrich endpoint.

    Setup: Create N records, then enrich them all in parallel.
    Verifies: All requests succeed, no connection pool exhaustion.
    """

    async def test_enrich_concurrent_requests_all_succeed(
        self, client: AsyncClient, db: AsyncSession, record_timestamp
    ) -> None:
        """Enrich N requests concurrently — all should succeed.

        Real-world: Data pipeline enriches 50 records by hitting an external API.
        Test: 5 concurrent POST /api/v2/records/enrich calls."""
        from services.ingestor.repositories import records as crud

        # Create 5 records
        records = []
        for i in range(5):
            record = await crud.create_record(
                db,
                RecordRequest(
                    source=f"concurrent-source-{i}",
                    timestamp=record_timestamp,
                    data={"index": i},
                ),
            )
            records.append(record)

        record_ids = [r.id for r in records]

        # Fire 5 concurrent enrich requests
        enrich_tasks = [
            client.post(
                "/api/v2/records/enrich",
                json={"record_ids": [record_ids[i]]},
            )
            for i in range(5)
        ]
        responses = await asyncio.gather(*enrich_tasks, return_exceptions=False)

        # All should return 200 OK
        for r in responses:
            assert r.status_code == 200, f"Enrich failed: {r.text}"
            data = r.json()
            assert "enriched_count" in data
            assert data["enriched_count"] == 1

    async def test_enrich_concurrent_batch_under_semaphore(
        self, client: AsyncClient, db: AsyncSession, record_timestamp
    ) -> None:
        """Concurrent enrich respects semaphore limit (default 10).

        Test: 20 concurrent tasks, each enriching 1 record.
        Expectation: All succeed via semaphore-controlled concurrency.

        Note: This test is designed for SQLite. On PostgreSQL with shared
        sessions, use client_isolated fixture instead (see postgresonly tests).
        """
        from services.ingestor.repositories import records as crud

        # Create 20 records
        records = []
        for i in range(20):
            record = await crud.create_record(
                db,
                RecordRequest(
                    source=f"semaphore-test-{i}",
                    timestamp=record_timestamp,
                    data={"index": i},
                ),
            )
            records.append(record)

        record_ids = [r.id for r in records]

        # Fire 20 concurrent enrich requests
        tasks = [
            client.post(
                "/api/v2/records/enrich",
                json={"record_ids": [record_ids[i]]},
            )
            for i in range(20)
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=False)

        # All should succeed
        assert len(responses) == 20
        for r in responses:
            assert r.status_code == 200, f"Enrich failed: {r.text}"


# ---------------------------------------------------------------------------
# TestRaceConditionHandling: Concurrent Upsert
# ---------------------------------------------------------------------------
@pytest.mark.integration
class TestRaceConditionHandling:
    """Test race condition handling for upsert endpoint.

    Pattern: Two concurrent upsert requests with same source+timestamp.
    Expected: One succeeds with 201 (create), one gets 200 (idempotent find).

    Note: Race tests may be skipped on SQLite due to session isolation
    limitations (see test_upsert_concurrent_same_key_one_wins for details).
    """

    @pytest.mark.postgresonly
    async def test_upsert_concurrent_same_key_idempotent_mode(
        self, client_isolated: AsyncClient
    ) -> None:
        """Idempotent mode race: one 201, one 200, same record returned.

        Real-world: Two webhooks arrive simultaneously with the same sensor data.
        Expected behavior: One creates; the other finds and returns it.

        Uses client_isolated fixture to ensure concurrent requests get
        independent PostgreSQL connections (avoids asyncpg conflict).
        """
        upsert_payload = {
            **_BASE_PAYLOAD,
            "source": "race-concurrent-idempotent",
            "timestamp": "2024-06-02T10:00:00",
        }

        # Fire both concurrently
        r1, r2 = await asyncio.gather(
            client_isolated.post("/api/v2/records/upsert", json=upsert_payload),
            client_isolated.post("/api/v2/records/upsert", json=upsert_payload),
        )

        statuses = sorted([r1.status_code, r2.status_code])

        # One should create (201), one should find existing (200)
        assert 200 in statuses and 201 in statuses, (
            f"Expected one 200 and one 201 in race condition, got {statuses}. "
            "Concurrent upserts should produce one create and one find."
        )

        # Both must return the same record (no duplicates)
        id1 = r1.json()["record"]["id"]
        id2 = r2.json()["record"]["id"]
        assert id1 == id2, (
            f"Duplicate records detected: IDs differ. "
            f"Race condition handling failed: {id1} != {id2}"
        )

    async def test_upsert_sequential_idempotency(self, client: AsyncClient) -> None:
        """Sequential upsert idempotency (control test for race condition).

        Real-world: Same sensor data arrives twice (delayed, not concurrent).
        Expected: First returns 201 (create), second returns 200 (find existing).

        Note: This test is designed for SQLite. On PostgreSQL with shared
        sessions, use client_isolated fixture with postgresonly marker.
        """
        upsert_payload = {
            **_BASE_PAYLOAD,
            "source": "sequential-idempotent",
            "timestamp": "2024-06-03T14:30:00",
        }

        # First request
        r1 = await client.post("/api/v2/records/upsert", json=upsert_payload)
        assert r1.status_code == 201, f"First upsert should create: {r1.text}"

        # Second request (same key)
        r2 = await client.post("/api/v2/records/upsert", json=upsert_payload)
        assert r2.status_code == 200, f"Second upsert should find existing: {r2.text}"

        # Both return same record
        id1 = r1.json()["record"]["id"]
        id2 = r2.json()["record"]["id"]
        assert id1 == id2

    @pytest.mark.postgresonly
    async def test_upsert_concurrent_different_keys_both_create(
        self, client_isolated: AsyncClient
    ) -> None:
        """Concurrent upserts with different keys: both should create (201).

        Real-world: Two different sensors send data simultaneously.
        Expected: Both create new records (no conflict).

        Uses client_isolated fixture to ensure concurrent requests get
        independent PostgreSQL connections (avoids asyncpg conflict).
        """
        payload1 = {
            **_BASE_PAYLOAD,
            "source": "sensor-1-concurrent",
            "timestamp": "2024-06-04T08:00:00",
        }
        payload2 = {
            **_BASE_PAYLOAD,
            "source": "sensor-2-concurrent",
            "timestamp": "2024-06-04T08:00:00",
        }

        # Fire both concurrently (different source = different keys)
        r1, r2 = await asyncio.gather(
            client_isolated.post("/api/v2/records/upsert", json=payload1),
            client_isolated.post("/api/v2/records/upsert", json=payload2),
        )

        # Both should create
        assert r1.status_code == 201
        assert r2.status_code == 201

        # Different records
        id1 = r1.json()["record"]["id"]
        id2 = r2.json()["record"]["id"]
        assert id1 != id2, "Different keys should create different records"

    async def test_upsert_strict_mode_sequential_conflict(
        self, client: AsyncClient
    ) -> None:
        """Strict mode rejects duplicates (sequential, control test).

        Real-world: Strict deduplication policy — no duplicates allowed.
        Expected: First returns 201, second returns 409.

        Note: This test is designed for SQLite. On PostgreSQL with shared
        sessions, use client_isolated fixture with postgresonly marker.
        """
        upsert_payload = {
            **_BASE_PAYLOAD,
            "source": "strict-sequential",
            "timestamp": "2024-06-05T16:45:00",
        }

        # First upsert (creates)
        r1 = await client.post(
            "/api/v2/records/upsert",
            params={"mode": "strict"},
            json=upsert_payload,
        )
        assert r1.status_code == 201

        # Second upsert (identical key — must fail in strict mode)
        r2 = await client.post(
            "/api/v2/records/upsert",
            params={"mode": "strict"},
            json=upsert_payload,
        )
        assert r2.status_code == 409, "Strict mode should reject duplicates"
        detail = r2.json()["detail"]
        # Detail is a dict with "error", "existing_id", "message"
        assert detail.get("error") == "conflict" or "conflict" in str(detail).lower()
