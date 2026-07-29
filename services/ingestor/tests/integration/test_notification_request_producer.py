"""PostgreSQL proof for transactional incident notification requests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.contracts.events import (
    EVENT_NOTIFICATION_DELIVERY_REQUESTED_V1,
    NotificationDeliveryRequestedV1,
)
from services.ingestor.api_schemas.scorecards import HealthSampleCreate
from services.ingestor.config import settings
from services.ingestor.incident_lifecycle import (
    enqueue_incident_notification_requests,
    record_health_sample,
)
from services.ingestor.models import (
    DependencyIncident,
    OutboxEvent,
    ProviderHealthSample,
    SourceProfile,
)
from services.ingestor.repositories.incidents import IncidentTransition


pytestmark = [pytest.mark.integration, pytest.mark.postgresonly]


def _failed_sample(source_id: int) -> HealthSampleCreate:
    return HealthSampleCreate(
        source_id=source_id,
        sampled_at=datetime(2026, 7, 29, 15, tzinfo=UTC),
        latency_ms=80,
        is_success=False,
        http_status=503,
        error_message="upstream unavailable",
    )


async def _source(db: AsyncSession) -> SourceProfile:
    source = SourceProfile(
        name="notification-producer-test",
        base_url="https://example.com",
        tenant_id=42,
        incident_failure_threshold=1,
        incident_cooldown_seconds=900,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


def _enable_broker_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "notifications_enabled", True)
    monkeypatch.setattr(settings, "notification_delivery_mode", "broker")
    monkeypatch.setattr(
        settings,
        "notification_default_channels",
        "webhook,email",
    )


async def test_broker_mode_adds_one_safe_idempotent_request_without_direct_send(
    postgresql_async_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = postgresql_async_session
    _enable_broker_delivery(monkeypatch)
    direct_dispatch = AsyncMock()
    monkeypatch.setattr(
        "services.ingestor.incident_lifecycle.dispatch_notification_event",
        direct_dispatch,
    )
    source = await _source(db)

    await record_health_sample(db, _failed_sample(source.id))

    incident = (await db.scalars(select(DependencyIncident))).one()
    outbox = (await db.scalars(select(OutboxEvent))).one()
    event = NotificationDeliveryRequestedV1.model_validate(outbox.payload)
    assert outbox.event_type == EVENT_NOTIFICATION_DELIVERY_REQUESTED_V1
    assert outbox.aggregate_type == "dependency_incident"
    assert outbox.aggregate_id == str(incident.id)
    assert outbox.idempotency_key == (
        f"notification-request:incident:{incident.id}:notification:1"
    )
    assert event.message_id == f"incident:{incident.id}:notification:1"
    assert event.payload.channels == ["webhook", "email"]
    assert event.payload.model_dump() == {
        "incident_id": incident.id,
        "source_id": source.id,
        "tenant_id": 42,
        "severity": "critical",
        "summary": "1 consecutive probes failed for notification-producer-test.",
        "trigger_type": "availability",
        "occurrence_count": 1,
        "guidance": incident.guidance,
        "channels": ["webhook", "email"],
    }
    assert incident.last_notification_at == incident.last_seen_at
    direct_dispatch.assert_not_awaited()

    transition = IncidentTransition(incident, "opened", True)
    await enqueue_incident_notification_requests(db, [transition])
    await enqueue_incident_notification_requests(db, [transition])
    await db.commit()
    count = await db.scalar(select(func.count(OutboxEvent.id)))
    assert count == 1


async def test_outbox_failure_rolls_back_sample_incident_and_request(
    postgresql_async_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = postgresql_async_session
    _enable_broker_delivery(monkeypatch)
    source = await _source(db)
    monkeypatch.setattr(
        "services.ingestor.incident_lifecycle.add_outbox_event",
        AsyncMock(side_effect=RuntimeError("outbox unavailable")),
    )

    with pytest.raises(RuntimeError, match="outbox unavailable"):
        await record_health_sample(db, _failed_sample(source.id))
    await db.rollback()

    assert await db.scalar(select(func.count(ProviderHealthSample.id))) == 0
    assert await db.scalar(select(func.count(DependencyIncident.id))) == 0
    assert await db.scalar(select(func.count(OutboxEvent.id))) == 0
