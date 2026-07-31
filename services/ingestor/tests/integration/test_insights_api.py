"""Integration tests for Insight Engine endpoints."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.integration


_SOURCE: dict[str, Any] = {
    "name": "insights-test-source",
    "base_url": "https://1.1.1.1",
    "health_check_path": "/insights",
}

_SCHEMA_V1: dict[str, Any] = {
    "id": 10,
    "status": "ok",
    "payload": {"region": "eu", "latency_ms": 100},
}

_SCHEMA_V2_BREAKING: dict[str, Any] = {
    "id": 10,
    "status": {"code": "ok"},
    "payload": {"region": "eu"},
}


async def _create_source(client: AsyncClient, name: str) -> int:
    response = await client.post("/api/v1/sources", json={**_SOURCE, "name": name})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


async def _seed_breaking_drift(client: AsyncClient, source_id: int) -> None:
    first = await client.post(
        "/api/v1/contracts/snapshots",
        json={
            "source_id": source_id,
            "schema_version": "v1",
            "payload_schema": _SCHEMA_V1,
        },
    )
    assert first.status_code == 201

    for _ in range(3):
        candidate = await client.post(
            "/api/v1/contracts/snapshots",
            json={
                "source_id": source_id,
                "schema_version": "v2",
                "payload_schema": _SCHEMA_V2_BREAKING,
            },
        )
        assert candidate.status_code == 201


class TestInsightFeeds:
    """Insight feed endpoints based on drift and source metadata."""

    async def test_anomaly_feed_empty(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/insights/anomalies")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["total"] == 0

    async def test_anomaly_feed_returns_items_after_drift(
        self, client: AsyncClient
    ) -> None:
        source_id = await _create_source(client, "insights-anomaly-source")
        await _seed_breaking_drift(client, source_id)

        response = await client.get("/api/v1/insights/anomalies")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 1
        first = body["items"][0]
        assert first["insight_type"] == "anomaly"
        assert first["source_id"] == source_id

    async def test_trend_feed_returns_compatibility_trend(
        self, client: AsyncClient
    ) -> None:
        source_id = await _create_source(client, "insights-trend-source")
        await _seed_breaking_drift(client, source_id)

        response = await client.get("/api/v1/insights/trends")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 1
        trend = next(item for item in body["items"] if item["source_id"] == source_id)
        assert trend["insight_type"] == "trend"
        assert trend["metric"] == "compatibility_score"
        assert trend["direction"] in {"up", "down", "flat"}

    async def test_recommendation_feed_returns_actions(
        self, client: AsyncClient
    ) -> None:
        source_id = await _create_source(client, "insights-recommendation-source")
        await _seed_breaking_drift(client, source_id)

        response = await client.get("/api/v1/insights/recommendations")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 1
        first = body["items"][0]
        assert first["insight_type"] == "recommendation"
        assert first["priority"] in {"P1", "P2", "P3"}
        assert isinstance(first["action"], str)
        assert first["action"]
