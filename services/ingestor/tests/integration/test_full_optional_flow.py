"""Deterministic composition proof for the optional operational flow."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.contracts.events import NotificationDeliveryRequestedV1
from services.ingestor.config import settings
from services.ingestor.models import AgentRun, OutboxEvent
from services.ingestor.notification_delivery_consumer import (
    NotificationProviderError,
    accept_notification_request,
    deliver_due_notifications,
)


pytestmark = [
    pytest.mark.integration,
    pytest.mark.postgresonly,
    pytest.mark.full_optional,
]

_NOW = datetime(2026, 8, 7, 12)
_BASELINE = {"status": "ok", "payload": {"temperature": 20.5, "region": "eu"}}
_BREAKING = {"status": {"code": "ok"}, "payload": {"region": "eu"}}


async def _confirm_breaking_drift(
    client: AsyncClient, source_id: int, payload_schema: dict[str, object]
) -> None:
    for _ in range(3):
        response = await client.post(
            "/api/v1/contracts/snapshots",
            json={"source_id": source_id, "payload_schema": payload_schema},
        )
        assert response.status_code == 201, response.text


async def test_breaking_drift_reaches_agent_handoff_and_durable_delivery(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compose RLS-scoped source, drift, agent handoff, and retry-safe delivery."""
    monkeypatch.setattr(settings, "rls_enabled", True)
    monkeypatch.setattr(settings, "notifications_enabled", True)
    monkeypatch.setattr(settings, "notification_delivery_mode", "broker")
    monkeypatch.setattr(settings, "notification_default_channels", "webhook")
    agent_trigger = MagicMock()
    monkeypatch.setattr(
        "services.ingestor.repositories.contract_drift._trigger_agent_run",
        agent_trigger,
    )

    source_response = await client.post(
        "/api/v1/sources",
        headers={"X-Tenant-ID": "77"},
        json={
            "name": "full-optional-source",
            "base_url": "https://1.1.1.1",
            "health_check_path": "/health",
            "probe_interval_seconds": 60,
            "incident_failure_threshold": 1,
        },
    )
    assert source_response.status_code == 201, source_response.text
    source_id = int(source_response.json()["id"])

    baseline = await client.post(
        "/api/v1/contracts/snapshots",
        json={"source_id": source_id, "payload_schema": _BASELINE},
    )
    assert baseline.status_code == 201
    assert baseline.json()["drift_event"] is None

    await _confirm_breaking_drift(client, source_id, _BREAKING)

    agent_run = (await db.scalars(select(AgentRun))).one()
    outbox = (await db.scalars(select(OutboxEvent))).one()
    assert agent_run.status == "pending"
    agent_trigger.assert_called_once_with(agent_run.id)

    event = NotificationDeliveryRequestedV1.model_validate(outbox.payload)
    accepted = await accept_notification_request(db, event)
    assert accepted.claimed is True
    assert accepted.delivery_count == 1

    async def unavailable(*_args: object) -> str:
        raise NotificationProviderError("transport", "timeout")

    retry = await deliver_due_notifications(
        db,
        unavailable,
        now=_NOW,
        retry_delay=lambda _attempt: timedelta(seconds=1),
    )
    assert retry.retried == 1

    delivered = await deliver_due_notifications(
        db,
        AsyncMock(return_value="test-harness-delivery-1"),
        now=_NOW + timedelta(seconds=1),
    )
    assert delivered.delivered == 1
