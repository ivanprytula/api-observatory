"""Integration tests for the Pillar 9 vector-search API routes."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import services.ingestor.vector_search as vector_search
from services.ingestor.api_schemas.records import RecordRequest
from services.ingestor.repositories import records as crud


@pytest.mark.integration
async def test_vector_search_index_records_endpoint(
    client: AsyncClient,
    db: AsyncSession,
    record_timestamp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = await crud.create_record(
        db,
        RecordRequest(
            source="vector-index",
            timestamp=record_timestamp,
            data={"summary": "hello vector"},
            tags=["semantic"],
        ),
    )

    async def _fake_index(
        records: list[Any], collection: str | None = None
    ) -> dict[str, Any]:
        assert len(records) == 1
        assert records[0].id == record.id
        return {"indexed_count": 1, "collection": collection or "records"}

    monkeypatch.setattr(vector_search, "index_record_documents", _fake_index)

    response = await client.post(
        "/api/v1/vector-search/index/records",
        json={"record_ids": [record.id, 99999]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["requested_count"] == 2
    assert body["indexed_count"] == 1
    assert body["missing_record_ids"] == [99999]
    assert body["collection"] == "records"


@pytest.mark.integration
async def test_vector_search_query_endpoint(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_search(
        query: str,
        top_k: int,
        collection: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assert query == "find alpha records"
        assert top_k == 3
        assert filters == {"must": [{"key": "source", "match": "vector-index"}]}
        return {
            "results": [
                {
                    "id": 7,
                    "score": 0.97,
                    "metadata": {"source": "vector-index", "tags": ["semantic"]},
                }
            ],
            "count": 1,
            "query": query,
        }

    monkeypatch.setattr(vector_search, "search_record_documents", _fake_search)

    response = await client.post(
        "/api/v1/vector-search/query",
        json={
            "query": "find alpha records",
            "top_k": 3,
            "filters": {"must": [{"key": "source", "match": "vector-index"}]},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["collection"] == "records"
    assert body["results"][0]["id"] == 7


@pytest.mark.integration
async def test_vector_search_health_endpoint(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_health() -> dict[str, Any]:
        return {"status": "ok", "qdrant_connected": True}

    monkeypatch.setattr(vector_search, "get_vector_search_health", _fake_health)

    response = await client.get("/api/v1/vector-search/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["inference_connected"] is True


@pytest.mark.integration
async def test_vector_search_index_recent_records_endpoint(
    client: AsyncClient,
    db: AsyncSession,
    record_timestamp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    older = await crud.create_record(
        db,
        RecordRequest(
            source="vector-recent",
            timestamp=record_timestamp,
            data={"summary": "older"},
            tags=["semantic"],
        ),
    )
    newer = await crud.create_record(
        db,
        RecordRequest(
            source="vector-recent",
            timestamp=record_timestamp.replace(hour=record_timestamp.hour + 1),
            data={"summary": "newer"},
            tags=["semantic"],
        ),
    )

    async def _fake_index(
        records: list[Any], collection: str | None = None
    ) -> dict[str, Any]:
        # Recent indexing should return latest records first.
        assert [record.id for record in records] == [newer.id]
        return {"indexed_count": len(records), "collection": collection or "records"}

    monkeypatch.setattr(vector_search, "index_record_documents", _fake_index)

    response = await client.post(
        "/api/v1/vector-search/index/recent",
        json={"source": "vector-recent", "limit": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["requested_count"] == 1
    assert body["indexed_count"] == 1
    assert body["missing_record_ids"] == []
    assert body["collection"] == "records"

    # Keep local references used to satisfy linting for setup data intent.
    assert older.id != newer.id
