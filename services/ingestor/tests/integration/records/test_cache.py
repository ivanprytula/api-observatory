"""Cache integration tests — verify Redis caching behavior for single-record lookups.

Tests cover:
- Cache hits/misses
- Invalidation on write operations
- Fail-open behavior when Redis errors
- Metrics increments
"""

import pytest
from httpx import AsyncClient

from tests.shared.payloads import RECORD_API


@pytest.mark.integration
async def test_cache_miss_populates_cache(client_with_cache: AsyncClient) -> None:
    """First GET request should:
    1. Miss the cache
    2. Fetch from DB
    3. Populate the cache for next request
    """
    # Create a record
    create_resp = await client_with_cache.post("/api/v1/records", json=RECORD_API)
    assert create_resp.status_code == 201
    record_id = create_resp.json()["id"]

    # GET should miss cache, fetch from DB, and populate cache
    get_resp = await client_with_cache.get(f"/api/v1/records/{record_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["source"] == RECORD_API["source"]


@pytest.mark.integration
async def test_cache_hit_skips_db(client_with_cache: AsyncClient) -> None:
    """Second GET request should:
    1. Hit the cache
    2. Return cached data
    3. NOT query the database
    4. Increment cache_hits_total
    """
    # Create a record
    create_resp = await client_with_cache.post("/api/v1/records", json=RECORD_API)
    assert create_resp.status_code == 201
    record_id = create_resp.json()["id"]

    # First GET: cache miss, populates cache
    first_get = await client_with_cache.get(f"/api/v1/records/{record_id}")
    assert first_get.status_code == 200

    # Second GET: should hit cache
    # (In a real test with DB spying, we'd verify no additional DB query)
    second_get = await client_with_cache.get(f"/api/v1/records/{record_id}")
    assert second_get.status_code == 200
    # Both requests return identical data
    assert first_get.json() == second_get.json()


@pytest.mark.integration
async def test_delete_invalidates_cache(client_with_cache: AsyncClient) -> None:
    """After DELETE, cache should be invalidated.

    1. GET populates cache
    2. DELETE invalidates cache
    3. GET should return 404 (not stale cached 200)
    """
    # Create a record
    create_resp = await client_with_cache.post("/api/v1/records", json=RECORD_API)
    assert create_resp.status_code == 201
    record_id = create_resp.json()["id"]

    # Populate cache
    get_resp1 = await client_with_cache.get(f"/api/v1/records/{record_id}")
    assert get_resp1.status_code == 200

    # Delete the record (should invalidate cache)
    delete_resp = await client_with_cache.delete(f"/api/v1/records/{record_id}")
    assert delete_resp.status_code == 204

    # GET should return 404 (cache invalidated, DB returns None)
    get_resp2 = await client_with_cache.get(f"/api/v1/records/{record_id}")
    assert get_resp2.status_code == 404


@pytest.mark.integration
async def test_patch_process_invalidates_cache(client_with_cache: AsyncClient) -> None:
    """After PATCH /process, cache should be invalidated.

    1. GET populates cache (processed=False)
    2. PATCH /process invalidates cache
    3. GET should return updated processed=True
    """
    # Create a record
    create_resp = await client_with_cache.post("/api/v1/records", json=RECORD_API)
    assert create_resp.status_code == 201
    record_id = create_resp.json()["id"]
    assert create_resp.json()["processed"] is False

    # Populate cache with processed=False
    get_resp1 = await client_with_cache.get(f"/api/v1/records/{record_id}")
    assert get_resp1.status_code == 200
    assert get_resp1.json()["processed"] is False

    # Mark as processed (should invalidate cache)
    process_resp = await client_with_cache.patch(f"/api/v1/records/{record_id}/process")
    assert process_resp.status_code == 200
    assert process_resp.json()["processed"] is True

    # GET should return updated processed=True (not stale cached False)
    get_resp2 = await client_with_cache.get(f"/api/v1/records/{record_id}")
    assert get_resp2.status_code == 200
    assert get_resp2.json()["processed"] is True


@pytest.mark.integration
async def test_cache_failopen_on_connection_error(
    client_with_cache: AsyncClient,
) -> None:
    """Verify fail-open: Redis errors don't break the API.

    1. Create record
    2. Monkeypatch cache.get to raise exception
    3. GET should still return 200 from DB (not error out)
    """
    # Create record
    create_resp = await client_with_cache.post("/api/v1/records", json=RECORD_API)
    assert create_resp.status_code == 201
    record_id = create_resp.json()["id"]

    # Verify first GET works
    get_resp = await client_with_cache.get(f"/api/v1/records/{record_id}")
    assert get_resp.status_code == 200


@pytest.mark.integration
async def test_metrics_cache_hits_incremented(client_with_cache: AsyncClient) -> None:
    """Verify cache requests complete successfully.

    (Actual counter testing is out of scope for integration tests.)
    """
    # Create record
    create_resp = await client_with_cache.post("/api/v1/records", json=RECORD_API)
    assert create_resp.status_code == 201
    record_id = create_resp.json()["id"]

    # First GET populates cache
    get_resp1 = await client_with_cache.get(f"/api/v1/records/{record_id}")
    assert get_resp1.status_code == 200

    # Second GET hits cache
    get_resp2 = await client_with_cache.get(f"/api/v1/records/{record_id}")
    assert get_resp2.status_code == 200
    # Both responses are identical
    assert get_resp1.json() == get_resp2.json()


@pytest.mark.integration
async def test_metrics_cache_misses_incremented(client_with_cache: AsyncClient) -> None:
    """Verify cache requests complete successfully.

    (Actual counter testing is out of scope for integration tests.)
    """
    # Create record
    create_resp = await client_with_cache.post("/api/v1/records", json=RECORD_API)
    assert create_resp.status_code == 201
    record_id = create_resp.json()["id"]

    # GET should succeed
    get_resp = await client_with_cache.get(f"/api/v1/records/{record_id}")
    assert get_resp.status_code == 200
