"""Async API integration tests."""

import asyncio
import logging
import time

import pytest
from httpx import AsyncClient

from tests.shared.payloads import RECORD_API


logger = logging.getLogger(__name__)


_RECORD = RECORD_API


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_health(client: AsyncClient) -> None:
    # Act
    r = await client.get("/health")

    # Assert
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


# ---------------------------------------------------------------------------
# Readiness Probe
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_readyz_returns_200_when_db_available(client: AsyncClient) -> None:
    """Readiness probe returns 200 when DB is reachable."""
    # Act
    r = await client.get("/readyz")

    # Assert
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["db"] == "ok"


@pytest.mark.integration
async def test_readyz_returns_503_when_db_unreachable() -> None:
    """Readiness probe returns 503 when DB is unreachable.

    This test simulates database failure by mocking the session's execute method
    to raise an exception. The /readyz endpoint should catch it and return 503.
    """
    from unittest.mock import AsyncMock

    from httpx import ASGITransport

    from services.ingestor.database import get_db
    from services.ingestor.main import app

    # Mock AsyncSession that raises when execute() is called
    mock_session = AsyncMock()
    mock_session.execute.side_effect = RuntimeError("Database connection lost")

    app.dependency_overrides[get_db] = lambda: mock_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Act
            r = await client.get("/readyz")

            # Assert
            assert r.status_code == 503
            body = r.json()
            assert body["detail"]["status"] == "degraded"
            assert body["detail"]["db"] == "unreachable"
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Create single record
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_create_record(client: AsyncClient) -> None:
    # Act
    r = await client.post("/api/v1/records", json=_RECORD)

    # Assert
    assert r.status_code == 201
    body = r.json()
    assert body["source"] == "api.example.com"
    assert body["tags"] == ["stock", "nasdaq"]
    assert body["id"] is not None
    assert body["processed"] is False


@pytest.mark.integration
async def test_create_record_missing_source(client: AsyncClient) -> None:
    bad = {**_RECORD}
    del bad["source"]

    r = await client.post("/api/v1/records", json=bad)

    assert r.status_code == 422


@pytest.mark.integration
async def test_create_record_empty_source(client: AsyncClient) -> None:
    r = await client.post("/api/v1/records", json={**_RECORD, "source": ""})

    assert r.status_code == 422


@pytest.mark.integration
async def test_create_record_future_timestamp(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/records", json={**_RECORD, "timestamp": "2099-01-01T00:00:00"}
    )

    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Batch create
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_create_batch(client: AsyncClient) -> None:
    payload = {"records": [_RECORD, {**_RECORD, "source": "b.example.com"}]}

    r = await client.post("/api/v1/records/batch", json=payload)

    assert r.status_code == 201
    assert r.json()["created"] == 2


@pytest.mark.integration
async def test_batch_too_large(client: AsyncClient) -> None:
    payload = {"records": [_RECORD] * 1001}

    r = await client.post("/api/v1/records/batch", json=payload)

    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Batch insert ?impl= toggle
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_batch_impl_optimized_returns_correct_count(client: AsyncClient) -> None:
    """optimized impl (INSERT RETURNING) — same contract as default."""
    payload = {"records": [_RECORD, {**_RECORD, "source": "opt.example.com"}]}

    r = await client.post("/api/v1/records/batch?impl=optimized", json=payload)

    assert r.status_code == 201
    body = r.json()
    assert body["created"] == 2
    assert body["impl"] == "optimized"


@pytest.mark.integration
async def test_batch_impl_naive_returns_correct_count(client: AsyncClient) -> None:
    """naive impl (add_all + N refreshes) — identical JSON output, different internals."""
    payload = {"records": [_RECORD, {**_RECORD, "source": "naive.example.com"}]}

    r = await client.post("/api/v1/records/batch?impl=naive", json=payload)

    assert r.status_code == 201
    body = r.json()
    assert body["created"] == 2
    assert body["impl"] == "naive"


@pytest.mark.integration
async def test_batch_impl_contract_identical(client: AsyncClient) -> None:
    """Both impls return the same JSON keys — the contract is impl-agnostic."""
    payload = {"records": [_RECORD]}

    r_opt = await client.post("/api/v1/records/batch?impl=optimized", json=payload)
    r_naive = await client.post("/api/v1/records/batch?impl=naive", json=payload)

    assert r_opt.status_code == 201
    assert r_naive.status_code == 201
    # Contract: both return {"created": int, "impl": str}
    assert set(r_opt.json().keys()) == set(r_naive.json().keys())
    assert r_opt.json()["created"] == r_naive.json()["created"]


@pytest.mark.integration
async def test_batch_impl_invalid_rejected(client: AsyncClient) -> None:
    """Unknown ?impl= value is rejected at the validation layer (422)."""
    payload = {"records": [_RECORD]}

    r = await client.post("/api/v1/records/batch?impl=magic", json=payload)

    assert r.status_code == 422


# ---------------------------------------------------------------------------
# List / pagination
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_list_records_empty(client: AsyncClient) -> None:
    r = await client.get("/api/v1/records")

    assert r.status_code == 200
    body = r.json()
    assert body["records"] == []
    assert body["pagination"]["total"] == 0
    assert body["pagination"]["has_more"] is False


@pytest.mark.integration
async def test_list_records_pagination(client: AsyncClient) -> None:
    for i in range(5):
        await client.post("/api/v1/records", json={**_RECORD, "source": f"src-{i}"})

    r = await client.get("/api/v1/records?skip=0&limit=3")

    body = r.json()
    assert len(body["records"]) == 3
    assert body["pagination"]["total"] == 5
    assert body["pagination"]["has_more"] is True


@pytest.mark.integration
async def test_list_records_filter_source(client: AsyncClient) -> None:
    await client.post("/api/v1/records", json={**_RECORD, "source": "alpha"})
    await client.post("/api/v1/records", json={**_RECORD, "source": "beta"})

    r = await client.get("/api/v1/records?source=alpha")

    body = r.json()
    assert len(body["records"]) == 1
    assert body["records"][0]["source"] == "alpha"


# Week 2 Milestone 2: Comprehensive pagination tests
@pytest.mark.integration
async def test_pagination_multi_page_traversal(client: AsyncClient) -> None:
    """Test cursor-based pagination across multiple pages.

    Creates 250 records and verifies we can traverse:
    Page 1 (0-99), Page 2 (100-199), Page 3 (200-249)
    """
    # Setup: Create 250 records
    for i in range(250):
        await client.post("/api/v1/records", json={**_RECORD, "data": {"idx": i}})

    # Page 1: skip=0, limit=100
    r1 = await client.get("/api/v1/records?skip=0&limit=100")
    body1 = r1.json()
    assert len(body1["records"]) == 100
    assert body1["pagination"]["skip"] == 0
    assert body1["pagination"]["limit"] == 100
    assert body1["pagination"]["total"] == 250
    assert body1["pagination"]["has_more"] is True  # 100 < 250

    # Page 2: skip=100, limit=100
    r2 = await client.get("/api/v1/records?skip=100&limit=100")
    body2 = r2.json()
    assert len(body2["records"]) == 100
    assert body2["pagination"]["skip"] == 100
    assert body2["pagination"]["has_more"] is True  # 200 < 250

    # Page 3: skip=200, limit=100 (partial page)
    r3 = await client.get("/api/v1/records?skip=200&limit=100")
    body3 = r3.json()
    assert len(body3["records"]) == 50  # Only 50 left
    assert body3["pagination"]["skip"] == 200
    assert body3["pagination"]["has_more"] is False  # 300 >= 250


@pytest.mark.integration
async def test_pagination_last_page_detection(client: AsyncClient) -> None:
    """Verify has_more is False on the last page."""
    # Setup: Create 50 records
    for i in range(50):
        await client.post("/api/v1/records", json={**_RECORD, "data": {"idx": i}})

    # Request with limit that exactly fits remaining records
    r = await client.get("/api/v1/records?skip=0&limit=50")
    body = r.json()
    assert len(body["records"]) == 50
    assert body["pagination"]["has_more"] is False


@pytest.mark.integration
async def test_pagination_boundary_conditions(client: AsyncClient) -> None:
    """Test edge cases: skip at boundary, limit at boundary."""
    # Setup: Create exactly 100 records
    for i in range(100):
        await client.post("/api/v1/records", json={**_RECORD, "data": {"idx": i}})

    # Skip to last record (99), request with limit=1
    r = await client.get("/api/v1/records?skip=99&limit=1")
    body = r.json()
    assert len(body["records"]) == 1
    assert body["pagination"]["has_more"] is False

    # Skip beyond all records (should return empty)
    r = await client.get("/api/v1/records?skip=100&limit=10")
    body = r.json()
    assert len(body["records"]) == 0
    assert body["pagination"]["total"] == 100
    assert body["pagination"]["has_more"] is False


@pytest.mark.integration
async def test_pagination_default_limit(client: AsyncClient) -> None:
    """Verify default limit is 100 when omitted."""
    # Setup: Create 150 records
    for i in range(150):
        await client.post("/api/v1/records", json={**_RECORD, "data": {"idx": i}})

    # Request without limit parameter (should default to 100)
    r = await client.get("/api/v1/records")
    body = r.json()
    assert len(body["records"]) == 100
    assert body["pagination"]["limit"] == 100
    assert body["pagination"]["has_more"] is True  # 100 < 150


@pytest.mark.integration
async def test_pagination_cursor_preservation(client: AsyncClient) -> None:
    """Verify pagination cursor (skip) is preserved accurately across requests."""
    # Setup: Create 35 records (will test page boundaries)
    for i in range(35):
        await client.post("/api/v1/records", json={**_RECORD, "source": f"src-{i % 5}"})

    # Get page 1
    r1 = await client.get("/api/v1/records?skip=0&limit=10")
    page1_ids = [rec["id"] for rec in r1.json()["records"]]

    # Get page 2 using returned skip
    r2 = await client.get("/api/v1/records?skip=10&limit=10")
    page2_ids = [rec["id"] for rec in r2.json()["records"]]

    # Get page 3 using returned skip
    r3 = await client.get("/api/v1/records?skip=20&limit=10")
    page3_ids = [rec["id"] for rec in r3.json()["records"]]

    # Get page 4 (partial)
    r4 = await client.get("/api/v1/records?skip=30&limit=10")
    page4_ids = [rec["id"] for rec in r4.json()["records"]]

    # Verify no overlaps and no gaps
    all_ids = page1_ids + page2_ids + page3_ids + page4_ids
    assert len(all_ids) == 35
    assert len(set(all_ids)) == 35  # All unique


# ---------------------------------------------------------------------------
# Get by ID
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_get_record(client: AsyncClient) -> None:
    created = (await client.post("/api/v1/records", json=_RECORD)).json()

    r = await client.get(f"/api/v1/records/{created['id']}")

    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


@pytest.mark.integration
async def test_get_nonexistent_record(client: AsyncClient) -> None:
    r = await client.get("/api/v1/records/99999")

    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Mark as processed
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_mark_processed(client: AsyncClient) -> None:
    created = (await client.post("/api/v1/records", json=_RECORD)).json()

    r = await client.patch(f"/api/v1/records/{created['id']}/process")

    assert r.status_code == 200
    assert r.json()["processed"] is True


@pytest.mark.integration
async def test_mark_processed_nonexistent(client: AsyncClient) -> None:
    r = await client.patch("/api/v1/records/99999/process")

    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_delete_record(client: AsyncClient) -> None:
    created = (await client.post("/api/v1/records", json=_RECORD)).json()

    r = await client.delete(f"/api/v1/records/{created['id']}")

    assert r.status_code == 204
    # Verify it's actually gone
    r = await client.get(f"/api/v1/records/{created['id']}")
    assert r.status_code == 404


@pytest.mark.integration
async def test_delete_record_not_found(client: AsyncClient) -> None:
    r = await client.delete("/api/v1/records/99999")

    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Archive (soft-delete)
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_archive_record(client: AsyncClient) -> None:
    created = (await client.post("/api/v1/records", json=_RECORD)).json()
    record_id = created["id"]

    r = await client.patch(f"/api/v1/records/{record_id}/archive")

    assert r.status_code == 200
    body = r.json()
    assert body["deleted_at"] is not None

    # Archived record is hidden from GET and list
    assert (await client.get(f"/api/v1/records/{record_id}")).status_code == 404
    listing = (await client.get("/api/v1/records")).json()
    assert all(rec["id"] != record_id for rec in listing["records"])


@pytest.mark.integration
async def test_archive_record_not_found(client: AsyncClient) -> None:
    r = await client.patch("/api/v1/records/99999/archive")

    assert r.status_code == 404


@pytest.mark.integration
async def test_archive_record_idempotent(client: AsyncClient) -> None:
    created = (await client.post("/api/v1/records", json=_RECORD)).json()
    record_id = created["id"]
    await client.patch(f"/api/v1/records/{record_id}/archive")

    # Second archive attempt returns 404 — already archived
    r = await client.patch(f"/api/v1/records/{record_id}/archive")

    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Rate Limiting & Endurance
# ---------------------------------------------------------------------------
# Week 2 Milestone 3: Endurance test (simulated)
@pytest.mark.integration
async def test_rate_limit_endurance_simulation(client: AsyncClient) -> None:
    """Simulate sustained load: 1050 requests to a rate-limited endpoint.

    This simulates Week 2 Milestone 3 completion criteria:
    "Endurance test: 1000 requests over 1 hour doesn't fail."

    In production, this would run for 1 hour at steady rate (17 req/sec).
    In tests, we send 1050 requests as fast as possible and verify:
      1. App doesn't crash (all requests complete)
      2. Early requests succeed (200 OK)
      3. Later requests hit rate limit (429)
      4. App remains healthy after load

    Rate limit: 100/minute on /health endpoint.
    Expected:
      - ~100 requests get 200 OK
      - ~950 requests get 429 (rate limited)
      - All requests complete without exception
      - Final health check passes
    """
    # Send 1050 requests rapidly to /health (rate limit: 100/minute)
    start = time.perf_counter()
    tasks = [client.get("/health") for _ in range(1050)]
    responses = await asyncio.gather(*tasks, return_exceptions=False)
    elapsed = time.perf_counter() - start

    # Process results
    status_codes = [r.status_code for r in responses]
    success_count = status_codes.count(200)
    rate_limit_count = status_codes.count(429)
    other_count = len(status_codes) - success_count - rate_limit_count

    # Log metrics
    logger.info(
        f"[Rate Limit Endurance] 1050 requests in {elapsed:.2f}s"
        f" | Success: {success_count}, RateLimit: {rate_limit_count}, Other: {other_count}"
    )

    # Assertions
    # 1. All requests completed (no exceptions, no timeouts)
    assert len(responses) == 1050, "All requests should complete"

    # 2. Early requests succeeded (rate limit allows ~100 per minute)
    assert success_count >= 50, (
        f"Expected ≥50 successful (200) responses, got {success_count}"
    )

    # 3. Most requests were rate-limited (expected behavior)
    assert rate_limit_count >= 800, (
        f"Expected ≥800 rate-limited (429) responses, got {rate_limit_count}"
    )

    # 4. No unexpected errors (should only be 200 or 429)
    assert other_count == 0, (
        f"Got unexpected status codes: {set(s for s in status_codes if s not in (200, 429))}"
    )

    # 5. All rate-limited responses have correct structure
    rate_limited_responses = [r for r in responses if r.status_code == 429]
    for r in rate_limited_responses:
        body = r.json()
        assert "detail" in body, "Rate-limit error should have detail field"

    # 6. App still healthy after load
    final_health = await client.get("/health")
    # Final health may be 200 or 429 (depends on rate limit state), but must not error
    assert final_health.status_code in (
        200,
        429,
    ), f"Final health check failed: {final_health.status_code}"


@pytest.mark.integration
async def test_rate_limit_429_response_format(client: AsyncClient) -> None:
    """Verify rate-limit (429) responses have documented error format.

    When a client exceeds the rate limit, they receive:
    - Status: 429 Too Many Requests
    - Body: JSON with 'detail' explaining the limit
    """
    # Exhaust rate limit (100/minute) by sending requests as fast as possible
    tasks = [client.get("/health") for _ in range(150)]
    responses = await asyncio.gather(*tasks)

    # Find a 429 response
    rate_limited_response = next((r for r in responses if r.status_code == 429), None)
    assert rate_limited_response is not None, "Should get at least one 429 response"

    # Verify structure
    body = rate_limited_response.json()
    assert "detail" in body
    assert isinstance(body["detail"], str)
    assert "rate limit" in body["detail"].lower()
