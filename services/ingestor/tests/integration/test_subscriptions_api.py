"""Integration tests for Subscription and Delivery endpoints."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from services.ingestor.config import settings


pytestmark = pytest.mark.integration


_SOURCE: dict[str, Any] = {
    "name": "subscriptions-test-source",
    "url": "https://api.example.com/subscriptions",
    "source_type": "rest",
    "tags": ["Subscriptions", "Test"],
}

_SCHEMA_V1: dict[str, Any] = {
    "id": 1,
    "status": "ok",
    "payload": {"region": "eu", "latency_ms": 100},
}

_SCHEMA_V2_BREAKING: dict[str, Any] = {
    "id": 1,
    "status": {"code": "ok"},
    "payload": {"region": "eu"},
}


async def _create_source(client: AsyncClient, name: str) -> int:
    response = await client.post("/api/v1/sources", json={**_SOURCE, "name": name})
    assert response.status_code == 201
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


class TestSubscriptionDelivery:
    """Read and test-delivery endpoints for subscription flow."""

    async def test_channel_configs_endpoint(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/subscriptions/channel-configs")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 4
        channels = {item["channel"] for item in body["items"]}
        assert {"webhook", "slack", "telegram", "email"}.issubset(channels)

    async def test_alert_policies_endpoint(self, client: AsyncClient) -> None:
        source_id = await _create_source(client, "subscriptions-policy-source")

        response = await client.get(
            f"/api/v1/subscriptions/alert-policies?source_id={source_id}"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["policy_id"] == f"policy-source-{source_id}"
        assert item["notification_rule"]["channels"]

    async def test_delivery_logs_endpoint(self, client: AsyncClient) -> None:
        source_id = await _create_source(client, "subscriptions-log-source")
        await _seed_breaking_drift(client, source_id)

        response = await client.get(
            f"/api/v1/subscriptions/delivery-logs?source_id={source_id}"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 1
        first = body["items"][0]
        assert first["event_type"] in {"breaking", "non_breaking"}
        assert first["status"] in {"delivered", "suppressed"}

    async def test_escalation_preview_endpoint(self, client: AsyncClient) -> None:
        source_id = await _create_source(client, "subscriptions-escalation-source")

        response = await client.post(
            "/api/v1/subscriptions/escalations/preview",
            json={
                "event": "drift_detected",
                "severity": "critical",
                "source_id": source_id,
                "channels": ["webhook", "slack", "email"],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["policy_id"] == f"policy-source-{source_id}"
        assert body["steps"]
        assert body["steps"][0]["channel"] == "webhook"
        assert body["steps"][0]["after_minutes"] == 0

    async def test_escalation_preview_returns_404_for_missing_source(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/subscriptions/escalations/preview",
            json={
                "event": "drift_detected",
                "severity": "critical",
                "source_id": 99999,
            },
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Source profile not found"

    async def test_test_delivery_endpoint_when_notifications_disabled(
        self, client: AsyncClient
    ) -> None:
        old = settings.notifications_enabled
        settings.notifications_enabled = False
        try:
            response = await client.post(
                "/api/v1/subscriptions/deliveries/test",
                json={
                    "event": "subscription_test",
                    "message": "subscription delivery test",
                    "severity": "warning",
                },
            )
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "suppressed"
            assert body["event_type"] == "subscription_test"
        finally:
            settings.notifications_enabled = old
