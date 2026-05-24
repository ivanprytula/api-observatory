"""Integration tests for Step 8 — concurrent record enrichment endpoint.

Tests POST /api/v2/records/enrich:
  - Happy path with mocked fetch
  - Partial failures (some records fail, others succeed)
  - Missing record IDs (not found in DB)
  - All records fail
  - Semaphore limits concurrency
  - Request validation (too many IDs, empty list)
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from services.ingestor.constants import ENRICH_MAX_IDS, ENRICH_SEMAPHORE_LIMIT
from tests.shared.payloads import RECORD_API


_URL = "/api/v2/records/enrich"
_RECORD = RECORD_API

# External API mock response
_MOCK_POST = {"id": 1, "title": "Mock Title", "body": "Mock body text"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _create_records(client: AsyncClient, n: int) -> list[int]:
    """Create n records and return their IDs."""
    ids = []
    for i in range(n):
        payload = {**_RECORD, "source": f"enrich-test-{i}"}
        r = await client.post("/api/v1/records", json=payload)
        assert r.status_code == 201
        ids.append(r.json()["id"])
    return ids


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_enrich_happy_path(client: AsyncClient) -> None:
    """All records enriched successfully — enriched_count == len(record_ids)."""
    ids = await _create_records(client, 3)

    with patch(
        "services.ingestor.fetch.fetch_with_retry", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = _MOCK_POST
        r = await client.post(_URL, json={"record_ids": ids})

    assert r.status_code == 200
    body = r.json()
    assert body["enriched_count"] == 3
    assert body["failed_count"] == 0
    assert body["duration_ms"] >= 0
    assert len(body["results"]) == 3

    # Verify per-record shape
    for result in body["results"]:
        assert result["enriched"] is True
        assert result["external_title"] == "Mock Title"
        assert result["external_body"] == "Mock body text"
        assert result["error"] is None


@pytest.mark.integration
async def test_enrich_single_record(client: AsyncClient) -> None:
    """Single record enriched returns 200 with 1 result."""
    ids = await _create_records(client, 1)

    with patch(
        "services.ingestor.fetch.fetch_with_retry", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = _MOCK_POST
        r = await client.post(_URL, json={"record_ids": ids})

    assert r.status_code == 200
    body = r.json()
    assert body["enriched_count"] == 1
    assert body["failed_count"] == 0
    assert len(body["results"]) == 1


# ---------------------------------------------------------------------------
# Partial failures
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_enrich_partial_failure(client: AsyncClient) -> None:
    """Some records fail — failed ones appear with enriched=False, others succeed."""
    ids = await _create_records(client, 4)

    call_count = 0

    async def flaky_fetch(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # Fail every other call
        if call_count % 2 == 0:
            raise Exception("Simulated external API failure")
        return _MOCK_POST

    with patch("services.ingestor.fetch.fetch_with_retry", side_effect=flaky_fetch):
        r = await client.post(_URL, json={"record_ids": ids})

    assert r.status_code == 200
    body = r.json()
    assert body["enriched_count"] + body["failed_count"] == 4
    assert body["failed_count"] > 0  # At least one failed
    assert body["enriched_count"] > 0  # At least one succeeded

    # Failed records have error populated
    failed = [res for res in body["results"] if not res["enriched"]]
    for f in failed:
        assert f["error"] is not None
        assert f["external_title"] is None


@pytest.mark.integration
async def test_enrich_all_fail(client: AsyncClient) -> None:
    """All enrichments fail — endpoint still returns 200 with failed_count = n."""
    ids = await _create_records(client, 2)

    with patch(
        "services.ingestor.fetch.fetch_with_retry",
        new_callable=AsyncMock,
        side_effect=Exception("All down"),
    ):
        r = await client.post(_URL, json={"record_ids": ids})

    assert r.status_code == 200
    body = r.json()
    assert body["enriched_count"] == 0
    assert body["failed_count"] == 2
    for result in body["results"]:
        assert result["enriched"] is False
        assert result["error"] == "All down"


# ---------------------------------------------------------------------------
# Missing / unknown record IDs
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_enrich_nonexistent_records(client: AsyncClient) -> None:
    """Non-existent record IDs are returned with enriched=False and 'not found' error."""
    with patch(
        "services.ingestor.fetch.fetch_with_retry", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = _MOCK_POST
        r = await client.post(_URL, json={"record_ids": [999999, 999998]})

    assert r.status_code == 200
    body = r.json()
    assert body["enriched_count"] == 0
    assert body["failed_count"] == 2
    for result in body["results"]:
        assert result["enriched"] is False
        assert "not found" in result["error"].lower()


@pytest.mark.integration
async def test_enrich_mixed_existing_and_missing(client: AsyncClient) -> None:
    """Mix of real and missing IDs — missing ones fail, real ones succeed."""
    ids = await _create_records(client, 2)
    mixed_ids = ids + [999999]  # append non-existent

    with patch(
        "services.ingestor.fetch.fetch_with_retry", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = _MOCK_POST
        r = await client.post(_URL, json={"record_ids": mixed_ids})

    assert r.status_code == 200
    body = r.json()
    assert body["enriched_count"] == 2
    assert body["failed_count"] == 1
    assert len(body["results"]) == 3


# ---------------------------------------------------------------------------
# Concurrency verification
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_enrich_respects_semaphore_limit(client: AsyncClient) -> None:
    """Concurrent inflight count never exceeds ENRICH_SEMAPHORE_LIMIT."""
    ids = await _create_records(client, ENRICH_SEMAPHORE_LIMIT + 5)

    concurrent_peak = 0
    current_concurrent = 0
    lock = asyncio.Lock()

    async def tracked_fetch(*args, **kwargs):
        nonlocal concurrent_peak, current_concurrent
        async with lock:
            current_concurrent += 1
            if current_concurrent > concurrent_peak:
                concurrent_peak = current_concurrent
        # Simulate small async work so concurrent count builds up
        await asyncio.sleep(0.01)
        async with lock:
            current_concurrent -= 1
        return _MOCK_POST

    with patch("services.ingestor.fetch.fetch_with_retry", side_effect=tracked_fetch):
        r = await client.post(_URL, json={"record_ids": ids})

    assert r.status_code == 200
    body = r.json()
    assert body["enriched_count"] == len(ids)
    # Verify semaphore worked: peak concurrency ≤ ENRICH_SEMAPHORE_LIMIT
    assert concurrent_peak <= ENRICH_SEMAPHORE_LIMIT


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_enrich_empty_list_rejected(client: AsyncClient) -> None:
    """Empty record_ids list is rejected with 422."""
    r = await client.post(_URL, json={"record_ids": []})
    assert r.status_code == 422


@pytest.mark.integration
async def test_enrich_too_many_ids_rejected(client: AsyncClient) -> None:
    """More than ENRICH_MAX_IDS record IDs are rejected with 422."""
    r = await client.post(_URL, json={"record_ids": list(range(ENRICH_MAX_IDS + 1))})
    assert r.status_code == 422


@pytest.mark.integration
async def test_enrich_missing_body_rejected(client: AsyncClient) -> None:
    """Missing request body is rejected with 422."""
    r = await client.post(_URL, json={})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Response shape verification
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_enrich_response_shape(client: AsyncClient) -> None:
    """Verify complete EnrichResponse shape is returned."""
    ids = await _create_records(client, 2)

    with patch(
        "services.ingestor.fetch.fetch_with_retry", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = _MOCK_POST
        r = await client.post(_URL, json={"record_ids": ids})

    assert r.status_code == 200
    body = r.json()

    # Top-level fields
    assert "enriched_count" in body
    assert "failed_count" in body
    assert "duration_ms" in body
    assert "results" in body

    # Per-record fields
    for result in body["results"]:
        assert "record_id" in result
        assert "source" in result
        assert "enriched" in result
        assert "error" in result
        assert "external_title" in result
        assert "external_body" in result
