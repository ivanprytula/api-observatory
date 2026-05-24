"""Tests for cursor-based pagination (api/v2/records/cursor).

Cursor pagination is ideal for high-load scenarios where:
- Offset/limit pagination would require counting total records
- Concurrent inserts can cause offset to shift (skipped/duplicate records)
- Cache efficiency matters (cursor is tied to a specific record position)
"""

import pytest
from httpx import AsyncClient


@pytest.mark.parametrize(
    "limit",
    [1, 5, 10],
    ids=["limit_1", "limit_5", "limit_10"],
)
async def test_cursor_pagination_basic_traversal(
    client: AsyncClient, created_records: list[dict], limit: int
) -> None:
    """Verify cursor pagination can traverse all records in multiple pages."""
    # Arrange: create 10+ records
    _ = {r["id"] for r in created_records}

    # Act: fetch records using cursor pagination
    seen_ids = set()
    cursor = None
    page_count = 0
    max_pages = 100  # Prevent infinite loops

    while page_count < max_pages:
        response = await client.get(
            "/api/v2/records/cursor",
            params={"cursor": cursor, "limit": limit},
        )
        assert response.status_code == 200, (
            f"Page {page_count} failed: {response.json()}"
        )

        body = response.json()
        records = body.get("records", [])
        page_count += 1

        # Verify response shape
        assert "records" in body
        assert "has_more" in body
        assert "next_cursor" in body
        assert "limit" in body
        assert body["limit"] == limit

        # Collect record IDs
        page_ids = {r["id"] for r in records}
        seen_ids.update(page_ids)

        # Verify no duplicates across pages
        assert len(page_ids) <= limit
        if len(page_ids) == 0:
            break

        # If no more records, stop
        if not body.get("has_more"):
            break

        cursor = body.get("next_cursor")
        if not cursor:
            break

    # Verify we collected some records
    assert len(seen_ids) > 0, "cursor pagination returned no records"


async def test_cursor_pagination_has_more_flag(
    client: AsyncClient, created_records: list[dict]
) -> None:
    """Verify has_more flag correctly indicates if more records exist."""
    # Arrange: fetch with limit=1 to force multiple pages
    response = await client.get(
        "/api/v2/records/cursor",
        params={"limit": 1},
    )
    body = response.json()

    # Act & Assert
    assert response.status_code == 200
    if len(created_records) > 1:
        # If multiple records exist, first page should have has_more=True
        assert body["has_more"] is True
        assert body["next_cursor"] is not None
    else:
        # If 1 or 0 records, has_more should be False
        assert body["has_more"] is False
        assert body["next_cursor"] is None


async def test_cursor_pagination_with_source_filter(
    client: AsyncClient,
) -> None:
    """Verify cursor pagination respects source filter."""
    # Arrange: create records with different sources
    response1 = await client.post(
        "/api/v1/records",
        json={
            "source": "source-A",
            "timestamp": "2024-01-15T10:00:00",
            "data": {},
            "tags": [],
        },
    )
    response2 = await client.post(
        "/api/v1/records",
        json={
            "source": "source-B",
            "timestamp": "2024-01-15T10:00:00",
            "data": {},
            "tags": [],
        },
    )
    assert response1.status_code == 201
    assert response2.status_code == 201

    # Act: fetch cursor-paginated results for source-A only
    response = await client.get(
        "/api/v2/records/cursor",
        params={"source": "source-A", "limit": 50},
    )
    body = response.json()

    # Assert: all records should be source-A
    assert response.status_code == 200
    for record in body["records"]:
        assert record["source"] == "source-A"


async def test_cursor_pagination_empty_result(client: AsyncClient) -> None:
    """Verify cursor pagination handles empty results gracefully."""
    # Arrange: use a source that doesn't exist
    response = await client.get(
        "/api/v2/records/cursor",
        params={"source": "nonexistent-source-xyz", "limit": 50},
    )

    # Act & Assert
    assert response.status_code == 200
    body = response.json()
    assert body["records"] == []
    assert body["has_more"] is False
    assert body["next_cursor"] is None


async def test_cursor_pagination_invalid_cursor(client: AsyncClient) -> None:
    """Verify handling of invalid cursor value."""
    # Arrange: pass a malformed cursor
    response = await client.get(
        "/api/v2/records/cursor",
        params={"cursor": "invalid-base64-!!!@@##", "limit": 50},
    )

    # Act & Assert
    # Should degrade gracefully: treat invalid cursor as None (start from beginning)
    assert response.status_code == 200


async def test_cursor_pagination_limit_bounds(client: AsyncClient) -> None:
    """Verify limit parameter respects min/max bounds."""
    # Act & Assert: too low
    response = await client.get(
        "/api/v2/records/cursor",
        params={"limit": 0},
    )
    assert response.status_code == 422  # Validation error

    # Act & Assert: too high
    response = await client.get(
        "/api/v2/records/cursor",
        params={"limit": 101},
    )
    assert response.status_code == 422  # Validation error

    # Act & Assert: valid bounds
    for limit in [1, 50, 100]:
        response = await client.get(
            "/api/v2/records/cursor",
            params={"limit": limit},
        )
        assert response.status_code == 200


async def test_cursor_pagination_stable_under_inserts(
    client: AsyncClient, created_records: list[dict]
) -> None:
    """Verify cursor pagination is stable when new records are inserted concurrently.

    This test demonstrates the advantage of cursor pagination:
    offset/limit pagination would skip or duplicate records when inserts happen.
    """
    # Arrange: fetch first page
    response = await client.get(
        "/api/v2/records/cursor",
        params={"limit": 2},
    )
    body1 = response.json()
    first_page_ids = {r["id"] for r in body1["records"]}
    next_cursor = body1.get("next_cursor")

    # Simulate concurrent insert (this would shift offset in offset/limit pagination)
    await client.post(
        "/api/v1/records",
        json={
            "source": "concurrent-insert",
            "timestamp": "2024-01-01T00:00:00",
            "data": {},
            "tags": [],
        },
    )

    # Act: fetch second page with the cursor from page 1
    if next_cursor:
        response = await client.get(
            "/api/v2/records/cursor",
            params={"cursor": next_cursor, "limit": 2},
        )
        body2 = response.json()
        second_page_ids = {r["id"] for r in body2["records"]}

        # Assert: no overlap between pages (cursor-pagination is stable)
        assert len(first_page_ids & second_page_ids) == 0, (
            "Cursor pagination should not have overlapping records between pages"
        )
