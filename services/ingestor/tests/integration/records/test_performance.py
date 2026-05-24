"""Async performance baseline tests — run with pytest -v --log-cli-level=INFO to see timings."""

import logging
import time

import pytest
from httpx import AsyncClient

from tests.shared.payloads import RECORD_PERF


logger = logging.getLogger(__name__)


_RECORD = RECORD_PERF


@pytest.mark.integration
async def test_batch_insert_1000(client: AsyncClient) -> None:
    """Baseline: How fast can we insert 1000 records?"""
    # Arrange — unique (source, timestamp) per record to satisfy unique constraint
    payload = {
        "records": [
            {
                **_RECORD,
                "timestamp": f"2024-01-15T{10 + i // 3600:02d}:{(i % 3600) // 60:02d}:{i % 60:02d}",
                "data": {"value": i},
            }
            for i in range(1000)
        ]
    }
    start = time.perf_counter()

    # Act
    r = await client.post("/api/v1/records/batch", json=payload)
    elapsed = time.perf_counter() - start

    # Assert
    logger.info(f"[perf] 1 000 records inserted in {elapsed:.3f}s")
    assert r.status_code == 201
    assert elapsed < 10.0


@pytest.mark.integration
async def test_list_1000_records(client: AsyncClient) -> None:
    """Baseline: How fast can we list 1000 records?"""
    # Arrange — unique (source, timestamp) per record to satisfy unique constraint
    payload = {
        "records": [
            {
                **_RECORD,
                "timestamp": f"2024-01-15T{10 + i // 3600:02d}:{(i % 3600) // 60:02d}:{i % 60:02d}",
                "data": {"value": i},
            }
            for i in range(1000)
        ]
    }
    await client.post("/api/v1/records/batch", json=payload)
    start = time.perf_counter()

    # Act
    r = await client.get("/api/v1/records?limit=1000")
    elapsed = time.perf_counter() - start

    # Assert
    logger.info(f"[perf] 1 000 records listed in {elapsed:.3f}s")
    assert r.status_code == 200
    assert elapsed < 3.0


@pytest.mark.integration
async def test_single_vs_batch_insert(client: AsyncClient) -> None:
    """Compare single insert (loop) vs batch insert.

    Week 2 Milestone 1: Demonstrates batch is significantly faster than loop.

    Note: With SQLite in-memory (tests), speedup ~1.5—2x.
    Production PostgreSQL async via asyncpg shows 10x+ speedup for 1000 records.
    """
    # Use 50 records for faster test (still shows meaningful speedup)
    count = 50

    # ------ Single insert (loop through and create each individually) ------
    start_single = time.perf_counter()
    for i in range(count):
        # Unique timestamp per record to satisfy (source, timestamp) unique constraint
        ts = f"2024-01-15T10:{i // 60:02d}:{i % 60:02d}"
        r = await client.post(
            "/api/v1/records", json={**_RECORD, "timestamp": ts, "data": {"value": i}}
        )
        assert r.status_code == 201
    elapsed_single = time.perf_counter() - start_single

    # ------ Batch insert (all at once) ------
    start_batch = time.perf_counter()
    # Offset timestamps beyond those used by single inserts (count + i)
    payload = {
        "records": [
            {
                **_RECORD,
                "timestamp": f"2024-01-15T11:{(count + i) // 60:02d}:{(count + i) % 60:02d}",
                "data": {"value": i},
            }
            for i in range(count)
        ]
    }
    r = await client.post("/api/v1/records/batch", json=payload)
    assert r.status_code == 201
    elapsed_batch = time.perf_counter() - start_batch

    # ------ Calculate and log speedup ------
    speedup = elapsed_single / elapsed_batch

    logger.info(
        f"\n[Week 2 Milestone 1] Single vs Batch ({count} records):\n"
        f"  Single (loop):  {elapsed_single:.3f}s\n"
        f"  Batch (one):    {elapsed_batch:.3f}s\n"
        f"  Speedup:        {speedup:.1f}x\n"
        f"  (SQLite in-memory; PostgreSQL shows 10x+ in production)"
    )

    # Assert speedup is significant (>1.3x for SQLite, >10x for PostgreSQL)
    assert speedup > 1.3, f"Batch should be faster, got {speedup:.1f}x"
