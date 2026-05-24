"""Integration tests for notification API routes (Pillar 8)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from services.ingestor.config import settings


@pytest.mark.integration
async def test_notifications_test_endpoint_when_disabled(client: AsyncClient) -> None:
    old_enabled = settings.notifications_enabled
    settings.notifications_enabled = False
    try:
        response = await client.post(
            "/api/v1/notifications/test",
            json={"message": "hello from test"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["sent"] == 0
        assert body["failed"] == 0
        assert body["detail"] == "notifications disabled"
    finally:
        settings.notifications_enabled = old_enabled
