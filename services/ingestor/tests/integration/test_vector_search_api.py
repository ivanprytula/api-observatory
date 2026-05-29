"""Integration tests for the Pillar 9 vector-search API routes."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import services.ingestor.vector_search as vector_search
from services.ingestor.api_schemas.observations import ObservationRequest
from services.ingestor.repositories import observations as crud


@pytest.mark.integration
async def test_vector_search_index_observations_endpoint(
    client: AsyncClient,
    db: AsyncSession,
    observation_timestamp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observation = await crud.create_observation(
        db,
        ObservationRequest(
            source="vector-index",
            timestamp=observation_timestamp,
            data={"summary": "hello vector"},
            tags=["semantic"],
        ),
    )

    async def _fake_index(
        observations: list[Any], collection: str | None = None
    ) -> dict[str, Any]:
        assert len(observations) == 1
        assert observations[0].id == observation.id
        return {"indexed_count": 1, "collection": collection or "observations"}

    monkeypatch.setattr(vector_search, "index_observation_documents", _fake_index)

    response = await client.post(
        "/api/v1/vector-search/index/observations",
        json={"observation_ids": [observation.id, 99999]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["requested_count"] == 2
    assert body["indexed_count"] == 1
    assert body["missing_observation_ids"] == [99999]
    assert body["collection"] == "observations"


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
        assert query == "find alpha observations"
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

    monkeypatch.setattr(vector_search, "search_observation_documents", _fake_search)

    response = await client.post(
        "/api/v1/vector-search/query",
        json={
            "query": "find alpha observations",
            "top_k": 3,
            "filters": {"must": [{"key": "source", "match": "vector-index"}]},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["collection"] == "observations"
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
async def test_vector_search_index_recent_observations_endpoint(
    client: AsyncClient,
    db: AsyncSession,
    observation_timestamp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    older = await crud.create_observation(
        db,
        ObservationRequest(
            source="vector-recent",
            timestamp=observation_timestamp,
            data={"summary": "older"},
            tags=["semantic"],
        ),
    )
    newer = await crud.create_observation(
        db,
        ObservationRequest(
            source="vector-recent",
            timestamp=observation_timestamp.replace(
                hour=observation_timestamp.hour + 1
            ),
            data={"summary": "newer"},
            tags=["semantic"],
        ),
    )

    async def _fake_index(
        observations: list[Any], collection: str | None = None
    ) -> dict[str, Any]:
        # Recent indexing should return latest observations first.
        assert [observation.id for observation in observations] == [newer.id]
        return {
            "indexed_count": len(observations),
            "collection": collection or "observations",
        }

    monkeypatch.setattr(vector_search, "index_observation_documents", _fake_index)

    response = await client.post(
        "/api/v1/vector-search/index/recent",
        json={"source": "vector-recent", "limit": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["requested_count"] == 1
    assert body["indexed_count"] == 1
    assert body["missing_observation_ids"] == []
    assert body["collection"] == "observations"

    # Keep local references used to satisfy linting for setup data intent.
    assert older.id != newer.id
