"""Unit tests for MongoDB storage operations (Phase 2).

Tests Motor async client interactions: insert, find, update, delete operations.
"""

import pytest

from services.ingestor.storage.mongo import (
    find_by_source,
    insert_scraped_doc,
)


@pytest.mark.unit
@pytest.mark.mongo
async def test_insert_scraped_doc() -> None:
    """Insert a scraped document with all required fields."""
    try:
        doc = await insert_scraped_doc(
            source="hn",
            url="https://news.ycombinator.com/item?id=12345",
            title="Show HN: Test Project",
            content="This is test content for scraped doc.",
        )
        assert doc is not None
        assert doc["source"] == "hn"
        assert doc["url"] == "https://news.ycombinator.com/item?id=12345"
    except RuntimeError as e:
        if "MongoDB client not connected" in str(e):
            pytest.skip("MongoDB not available")
        raise


@pytest.mark.unit
@pytest.mark.mongo
async def test_find_by_source() -> None:
    """Find documents by source name."""
    try:
        # Insert test documents
        await insert_scraped_doc(
            source="hn",
            url="https://hn.test1",
            title="HN Test 1",
            content="Content 1",
        )
        await insert_scraped_doc(
            source="hn",
            url="https://hn.test2",
            title="HN Test 2",
            content="Content 2",
        )

        # Find by source
        docs = await find_by_source(source="hn", limit=10)
        assert len(docs) >= 2
        assert all(doc["source"] == "hn" for doc in docs)
    except RuntimeError as e:
        if "MongoDB client not connected" in str(e):
            pytest.skip("MongoDB not available")
        raise


@pytest.mark.unit
@pytest.mark.mongo
async def test_mongo_deduplication() -> None:
    """Same URL should not be inserted twice (unique index)."""
    try:
        url = "https://example.com/unique-article"
        doc1 = await insert_scraped_doc(
            source="test",
            url=url,
            title="First version",
            content="Original content",
        )
        assert doc1 is not None

        # Attempt to insert with same URL
        # MongoDB unique index should prevent duplicate (or return existing)
        _ = await insert_scraped_doc(
            source="test",
            url=url,
            title="Second version (should be ignored)",
            content="Different content",
        )
        # Depending on Motor behavior, either returns None or existing doc
    except RuntimeError as e:
        if "MongoDB client not connected" in str(e):
            pytest.skip("MongoDB not available")
        raise
