"""PostgreSQL proof for bounded notification outbox publishing."""

import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from libs.contracts.events import (
    EVENT_NOTIFICATION_DELIVERY_DEAD_LETTERED_V1,
    EVENT_NOTIFICATION_DELIVERY_REQUESTED_V1,
    TOPIC_NOTIFICATION_DELIVERY_DLQ_V1,
    TOPIC_NOTIFICATION_DELIVERY_REQUESTS_V1,
)
from services.ingestor.models import OutboxEvent
from services.ingestor.notification_outbox_publisher import (
    OutboxPublishBatchResult,
    publish_notification_outbox_batch,
)
from services.ingestor.repositories.messaging import add_outbox_event


pytestmark = [pytest.mark.integration, pytest.mark.postgresonly]

_NOW = datetime(2026, 7, 29, 16, 0, 0)


async def _add_event(
    db: AsyncSession,
    *,
    event_type: str,
    message_id: str,
) -> OutboxEvent:
    return await add_outbox_event(
        db,
        aggregate_type="dependency_incident",
        aggregate_id="7",
        event_type=event_type,
        payload={"event_type": event_type, "message_id": message_id, "payload": {}},
        idempotency_key=message_id,
        tenant_id=11,
    )


async def test_batch_publishes_only_supported_notification_events(
    postgresql_async_session: AsyncSession,
) -> None:
    db = postgresql_async_session
    request = await _add_event(
        db,
        event_type=EVENT_NOTIFICATION_DELIVERY_REQUESTED_V1,
        message_id="notification-request:7",
    )
    dead_letter = await _add_event(
        db,
        event_type=EVENT_NOTIFICATION_DELIVERY_DEAD_LETTERED_V1,
        message_id="notification-dlq:8",
    )
    unrelated = await _add_event(
        db,
        event_type="observation.created",
        message_id="observation:9",
    )
    await db.commit()
    publish = AsyncMock()

    result = await publish_notification_outbox_batch(db, publish, now=_NOW)

    assert result == OutboxPublishBatchResult(
        claimed=2,
        published=2,
        failed=0,
        claim_conflicts=0,
    )
    assert [call.args[0] for call in publish.await_args_list] == [
        TOPIC_NOTIFICATION_DELIVERY_REQUESTS_V1,
        TOPIC_NOTIFICATION_DELIVERY_DLQ_V1,
    ]
    assert [json.loads(call.args[1]) for call in publish.await_args_list] == [
        request.payload,
        dead_letter.payload,
    ]
    await db.refresh(unrelated)
    assert unrelated.published_at is None
    assert unrelated.publish_attempts == 0


async def test_failure_is_safely_scheduled_and_retried_when_due(
    postgresql_async_session: AsyncSession,
) -> None:
    db = postgresql_async_session
    event = await _add_event(
        db,
        event_type=EVENT_NOTIFICATION_DELIVERY_REQUESTED_V1,
        message_id="notification-request:retry",
    )
    await db.commit()
    failed_publish = AsyncMock(
        side_effect=RuntimeError("secret broker detail must not be persisted")
    )

    failed = await publish_notification_outbox_batch(
        db,
        failed_publish,
        now=_NOW,
    )
    assert failed.failed == 1
    await db.refresh(event)
    assert event.publish_attempts == 1
    assert event.last_error == "RuntimeError: publish failed"
    assert event.next_attempt_at == _NOW + timedelta(seconds=5)

    early_publish = AsyncMock()
    early = await publish_notification_outbox_batch(
        db,
        early_publish,
        now=_NOW + timedelta(seconds=4),
    )
    assert early.claimed == 0
    early_publish.assert_not_awaited()

    successful_publish = AsyncMock()
    retried = await publish_notification_outbox_batch(
        db,
        successful_publish,
        now=_NOW + timedelta(seconds=5),
    )
    assert retried.published == 1
    await db.refresh(event)
    assert event.publish_attempts == 2
    assert event.published_at == _NOW + timedelta(seconds=5)
    assert event.last_error is None


async def test_publish_call_has_a_bounded_timeout(
    postgresql_async_session: AsyncSession,
) -> None:
    db = postgresql_async_session
    event = await _add_event(
        db,
        event_type=EVENT_NOTIFICATION_DELIVERY_REQUESTED_V1,
        message_id="notification-request:timeout",
    )
    await db.commit()

    async def stalled_publish(_topic: str, _value: bytes) -> None:
        await asyncio.sleep(1)

    result = await publish_notification_outbox_batch(
        db,
        stalled_publish,
        publish_timeout_seconds=0.01,
        now=_NOW,
    )

    assert result.failed == 1
    await db.refresh(event)
    assert event.last_error == "TimeoutError: publish failed"
    assert event.next_attempt_at == _NOW + timedelta(seconds=5)
