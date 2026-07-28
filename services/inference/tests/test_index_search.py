"""Integration tests for /index and /search — the exact contract
`services.ingestor.vector_search` depends on."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.routing import Route

from services.inference.main import app
from services.inference.models import IndexedDocument


def test_metrics_endpoint_is_exposed() -> None:
    metrics_route = next(
        route
        for route in app.routes
        if isinstance(route, Route) and route.path == "/metrics"
    )

    assert metrics_route.methods is not None
    assert "GET" in metrics_route.methods


@pytest.mark.usefixtures("mock_embeddings")
class TestIndexEndpoint:
    async def test_index_creates_rows(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        response = await client.post(
            "/index",
            json={
                "collection": "docs",
                "documents": [
                    {"id": 1, "text": "apple banana", "metadata": {"kind": "fruit"}},
                    {"id": 2, "text": "cherry date", "metadata": {"kind": "fruit"}},
                ],
            },
        )

        assert response.status_code == 201
        assert response.json() == {"collection": "docs", "indexed": 2}

        rows = (
            (
                await db.execute(
                    select(IndexedDocument).where(IndexedDocument.collection == "docs")
                )
            )
            .scalars()
            .all()
        )
        assert {row.external_id for row in rows} == {1, 2}

    async def test_index_empty_documents_is_a_no_op(self, client: AsyncClient) -> None:
        response = await client.post(
            "/index", json={"collection": "docs", "documents": []}
        )
        assert response.status_code == 201
        assert response.json() == {"collection": "docs", "indexed": 0}

    async def test_reindexing_same_external_id_upserts(
        self, client: AsyncClient, db: AsyncSession
    ) -> None:
        await client.post(
            "/index",
            json={
                "collection": "docs",
                "documents": [{"id": 1, "text": "original text"}],
            },
        )
        response = await client.post(
            "/index",
            json={
                "collection": "docs",
                "documents": [{"id": 1, "text": "updated text"}],
            },
        )

        assert response.status_code == 201
        rows = (
            (
                await db.execute(
                    select(IndexedDocument).where(
                        IndexedDocument.collection == "docs",
                        IndexedDocument.external_id == 1,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].text == "updated text"


@pytest.mark.usefixtures("mock_embeddings")
class TestSearchEndpoint:
    async def test_search_ranks_lexically_closer_document_first(
        self, client: AsyncClient
    ) -> None:
        await client.post(
            "/index",
            json={
                "collection": "incidents",
                "documents": [
                    {"id": 101, "text": "payments api breaking schema drift"},
                    {"id": 102, "text": "weather api minor non breaking update"},
                ],
            },
        )

        response = await client.post(
            "/search",
            json={
                "query": "breaking schema drift",
                "top_k": 2,
                "collection": "incidents",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["collection"] == "incidents"
        assert len(body["results"]) == 2
        assert body["results"][0]["id"] == 101
        assert body["results"][0]["text"] == "payments api breaking schema drift"

    async def test_search_scoped_to_collection(self, client: AsyncClient) -> None:
        await client.post(
            "/index",
            json={
                "collection": "collection-a",
                "documents": [{"id": 1, "text": "shared word alpha"}],
            },
        )
        await client.post(
            "/index",
            json={
                "collection": "collection-b",
                "documents": [{"id": 2, "text": "shared word beta"}],
            },
        )

        response = await client.post(
            "/search",
            json={"query": "shared word", "top_k": 5, "collection": "collection-a"},
        )

        body = response.json()
        assert len(body["results"]) == 1
        assert body["results"][0]["id"] == 1

    async def test_search_empty_collection_returns_no_results(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/search",
            json={"query": "anything", "top_k": 5, "collection": "never-indexed"},
        )
        assert response.status_code == 200
        assert response.json()["results"] == []

    async def test_search_filters_by_metadata(self, client: AsyncClient) -> None:
        await client.post(
            "/index",
            json={
                "collection": "filtered",
                "documents": [
                    {
                        "id": 1,
                        "text": "shared word one",
                        "metadata": {"severity": "critical"},
                    },
                    {
                        "id": 2,
                        "text": "shared word two",
                        "metadata": {"severity": "low"},
                    },
                ],
            },
        )

        response = await client.post(
            "/search",
            json={
                "query": "shared word",
                "top_k": 5,
                "collection": "filtered",
                "filters": {"severity": "critical"},
            },
        )

        body = response.json()
        assert len(body["results"]) == 1
        assert body["results"][0]["id"] == 1
