"""PostgreSQL proof for durable notification delivery foundations."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from libs.contracts.events import (
    EVENT_NOTIFICATION_DELIVERY_DEAD_LETTERED_V1,
    NotificationDeliveryRequestedV1,
)
from services.ingestor.models import (
    InboxConsumption,
    NotificationDelivery,
    OutboxEvent,
)
from services.ingestor.notification_delivery_consumer import (
    NotificationProviderError,
    accept_notification_request,
    deliver_due_notifications,
)
from services.ingestor.notification_delivery_worker import process_notification_record
from services.ingestor.repositories.messaging import (
    add_outbox_event,
    claim_pending_outbox_events,
)
from services.ingestor.repositories.notification_delivery import (
    add_channel_deliveries,
    claim_due_deliveries,
    claim_notification_request,
    dead_letter_delivery,
    mark_delivery_delivered,
    schedule_delivery_retry,
)


pytestmark = [
    pytest.mark.integration,
    pytest.mark.postgresonly,
    pytest.mark.capability_broker,
]


_NOW = datetime(2026, 7, 29, 12, 0, 0)


def _request_event(
    *, channels: list[str] | None = None
) -> NotificationDeliveryRequestedV1:
    return NotificationDeliveryRequestedV1.model_validate(
        {
            "message_id": "incident:7:notification:2",
            "occurred_at": datetime(2026, 7, 29, 12, tzinfo=UTC),
            "payload": {
                "incident_id": 7,
                "source_id": 3,
                "tenant_id": 11,
                "severity": "critical",
                "summary": "Dependency unavailable.",
                "trigger_type": "availability",
                "occurrence_count": 2,
                "guidance": "Verify the dependency independently.",
                "channels": channels or ["webhook"],
            },
        }
    )


async def _create_deliveries(
    db: AsyncSession,
    *,
    channels: list[str] | None = None,
) -> tuple[InboxConsumption, list[NotificationDelivery]]:
    event = _request_event(channels=channels)
    inbox, claimed = await claim_notification_request(db, event, now=_NOW)
    assert claimed is True
    deliveries = await add_channel_deliveries(db, inbox, event)
    await db.commit()
    return inbox, deliveries


async def test_outbox_add_is_idempotent_and_caller_owned(
    postgresql_async_session: AsyncSession,
) -> None:
    db = postgresql_async_session
    rolled_back = await add_outbox_event(
        db,
        aggregate_type="incident",
        aggregate_id="7",
        event_type="notification.delivery_requested.v1",
        payload={"message_id": "rollback"},
        idempotency_key="notification-request:rollback",
        tenant_id=11,
    )
    rolled_back_id = rolled_back.id
    await db.rollback()
    assert await db.get(OutboxEvent, rolled_back_id) is None

    first = await add_outbox_event(
        db,
        aggregate_type="incident",
        aggregate_id="7",
        event_type="notification.delivery_requested.v1",
        payload={"message_id": "stable"},
        idempotency_key="notification-request:stable",
        tenant_id=11,
    )
    duplicate = await add_outbox_event(
        db,
        aggregate_type="incident",
        aggregate_id="7",
        event_type="notification.delivery_requested.v1",
        payload={"message_id": "stable"},
        idempotency_key="notification-request:stable",
        tenant_id=11,
    )
    assert first.id == duplicate.id
    await db.commit()


async def test_outbox_claim_lease_blocks_then_allows_reclaim(
    postgresql_async_session: AsyncSession,
) -> None:
    db = postgresql_async_session
    event = await add_outbox_event(
        db,
        aggregate_type="incident",
        aggregate_id="8",
        event_type="notification.delivery_requested.v1",
        payload={"message_id": "lease"},
        idempotency_key="notification-request:lease",
    )
    await db.commit()

    first = await claim_pending_outbox_events(
        db,
        claim_token="publisher-a",
        lease_seconds=30,
        now=_NOW,
    )
    assert event.id in {item.id for item in first}
    blocked = await claim_pending_outbox_events(
        db,
        claim_token="publisher-b",
        now=_NOW + timedelta(seconds=29),
    )
    assert event.id not in {item.id for item in blocked}
    reclaimed = await claim_pending_outbox_events(
        db,
        claim_token="publisher-b",
        now=_NOW + timedelta(seconds=30),
    )
    reclaimed_event = next(item for item in reclaimed if item.id == event.id)
    assert reclaimed_event.claim_token == "publisher-b"
    assert reclaimed_event.publish_attempts == 2


async def test_inbox_claim_and_channel_creation_are_idempotent(
    postgresql_async_session: AsyncSession,
) -> None:
    db = postgresql_async_session
    event = _request_event(channels=["webhook", "email"])

    inbox, claimed = await claim_notification_request(db, event, now=_NOW)
    assert claimed is True
    _, duplicate_claim = await claim_notification_request(
        db,
        event,
        now=_NOW + timedelta(seconds=29),
    )
    assert duplicate_claim is False
    reclaimed, reclaimed_claim = await claim_notification_request(
        db,
        event,
        now=_NOW + timedelta(seconds=30),
    )
    assert reclaimed_claim is True
    assert reclaimed.id == inbox.id

    first = await add_channel_deliveries(db, reclaimed, event)
    second = await add_channel_deliveries(db, reclaimed, event)
    await db.commit()
    assert [item.channel for item in first] == ["email", "webhook"]
    assert [item.id for item in first] == [item.id for item in second]


async def test_delivery_retry_is_due_only_after_schedule(
    postgresql_async_session: AsyncSession,
) -> None:
    db = postgresql_async_session
    inbox, deliveries = await _create_deliveries(db)
    delivery = deliveries[0]

    claimed = await claim_due_deliveries(
        db,
        claim_token="worker-a",
        now=_NOW,
    )
    assert [item.id for item in claimed] == [delivery.id]
    retry_at = _NOW + timedelta(seconds=30)
    retry = await schedule_delivery_retry(
        db,
        delivery_id=delivery.id,
        claim_token="worker-a",
        next_attempt_at=retry_at,
        error_category="transport",
        error_code="timeout",
        error_detail="provider request timed out",
    )
    assert retry is not None
    assert retry.status == "retry_scheduled"

    early = await claim_due_deliveries(
        db,
        claim_token="worker-b",
        now=retry_at - timedelta(seconds=1),
    )
    assert early == []
    due = await claim_due_deliveries(
        db,
        claim_token="worker-b",
        now=retry_at,
    )
    assert [item.id for item in due] == [delivery.id]
    assert due[0].attempt_count == 2

    completed = await mark_delivery_delivered(
        db,
        delivery_id=delivery.id,
        claim_token="worker-b",
        provider_reference="provider-message-7",
        now=retry_at,
    )
    assert completed is not None
    assert completed.status == "delivered"
    refreshed_inbox = await db.get(InboxConsumption, inbox.id)
    assert refreshed_inbox is not None
    assert refreshed_inbox.status == "completed"


async def test_expired_processing_delivery_is_reclaimed_as_the_same_attempt(
    postgresql_async_session: AsyncSession,
) -> None:
    db = postgresql_async_session
    _, deliveries = await _create_deliveries(db)
    delivery = deliveries[0]

    first = await claim_due_deliveries(
        db,
        claim_token="worker-a",
        lease_seconds=30,
        now=_NOW,
    )
    assert [item.id for item in first] == [delivery.id]
    assert first[0].attempt_count == 1

    blocked = await claim_due_deliveries(
        db,
        claim_token="worker-b",
        now=_NOW + timedelta(seconds=29),
    )
    assert blocked == []

    reclaimed = await claim_due_deliveries(
        db,
        claim_token="worker-b",
        now=_NOW + timedelta(seconds=30),
    )
    assert [item.id for item in reclaimed] == [delivery.id]
    assert reclaimed[0].claim_token == "worker-b"
    assert reclaimed[0].attempt_count == 1


async def test_dead_letter_state_and_sanitized_outbox_are_atomic_and_idempotent(
    postgresql_async_session: AsyncSession,
) -> None:
    db = postgresql_async_session
    inbox, deliveries = await _create_deliveries(db)
    delivery = deliveries[0]
    await claim_due_deliveries(db, claim_token="worker-a", now=_NOW)

    result = await dead_letter_delivery(
        db,
        delivery_id=delivery.id,
        claim_token="worker-a",
        error_category="configuration",
        error_code="missing_destination",
        error_detail="configured destination is unavailable",
        now=_NOW,
    )
    assert result is not None
    dead_letter, outbox = result
    assert dead_letter.status == "dead_letter"
    assert outbox.event_type == EVENT_NOTIFICATION_DELIVERY_DEAD_LETTERED_V1
    assert outbox.payload["payload"] == {
        "delivery_id": delivery.id,
        "request_message_id": delivery.message_id,
        "incident_id": 7,
        "source_id": 3,
        "tenant_id": 11,
        "channel": "webhook",
        "attempt_count": 1,
        "error_category": "configuration",
        "error_code": "missing_destination",
        "first_attempt_at": "2026-07-29T12:00:00Z",
        "last_attempt_at": "2026-07-29T12:00:00Z",
    }
    prohibited = {
        "destination",
        "authorization",
        "provider_response",
        "original_payload",
    }
    assert prohibited.isdisjoint(outbox.payload)
    assert prohibited.isdisjoint(outbox.payload["payload"])

    duplicate = await dead_letter_delivery(
        db,
        delivery_id=delivery.id,
        claim_token="worker-a",
        error_category="configuration",
        error_code="missing_destination",
        error_detail="duplicate",
        now=_NOW,
    )
    assert duplicate is None
    outbox_count = await db.scalar(
        select(func.count(OutboxEvent.id)).where(
            OutboxEvent.idempotency_key == f"notification-delivery-dlq:{delivery.id}"
        )
    )
    assert outbox_count == 1
    refreshed_inbox = await db.get(InboxConsumption, inbox.id)
    assert refreshed_inbox is not None
    assert refreshed_inbox.status == "dead_letter"


async def test_mixed_channel_outcomes_update_inbox_aggregate(
    postgresql_async_session: AsyncSession,
) -> None:
    db = postgresql_async_session
    inbox, deliveries = await _create_deliveries(
        db,
        channels=["webhook", "email"],
    )
    claimed = await claim_due_deliveries(
        db,
        claim_token="worker-a",
        now=_NOW,
    )
    by_channel = {item.channel: item for item in claimed}
    await mark_delivery_delivered(
        db,
        delivery_id=by_channel["email"].id,
        claim_token="worker-a",
        now=_NOW,
    )
    await dead_letter_delivery(
        db,
        delivery_id=by_channel["webhook"].id,
        claim_token="worker-a",
        error_category="provider",
        error_code="rejected",
        error_detail="provider rejected the request",
        now=_NOW,
    )

    refreshed_inbox = await db.get(InboxConsumption, inbox.id)
    assert refreshed_inbox is not None
    assert refreshed_inbox.status == "completed_with_dead_letters"
    assert {item.id for item in deliveries} == {
        by_channel["email"].id,
        by_channel["webhook"].id,
    }


async def test_consumer_orchestration_persists_acceptance_and_provider_outcomes(
    postgresql_async_session: AsyncSession,
) -> None:
    db = postgresql_async_session
    event = _request_event(channels=["webhook", "email"])

    accepted = await accept_notification_request(db, event.model_dump(mode="json"))
    duplicate = await accept_notification_request(db, event)
    assert accepted.claimed is True
    assert accepted.delivery_count == 2
    assert duplicate.claimed is False

    async def provider(
        delivery: NotificationDelivery,
        request: NotificationDeliveryRequestedV1,
    ) -> str:
        assert request.payload.summary == "Dependency unavailable."
        if delivery.channel == "email":
            raise NotificationProviderError(
                "configuration", "missing_sender", retryable=False
            )
        return "provider-message-1"

    result = await deliver_due_notifications(
        db,
        provider,
        claim_token="consumer-a",
    )
    assert result.claimed == 2
    assert result.delivered == 1
    assert result.dead_lettered == 1

    inbox = await db.get(InboxConsumption, accepted.inbox_id)
    assert inbox is not None
    assert inbox.status == "completed_with_dead_letters"


async def test_consumer_orchestration_schedules_then_dead_letters_retries(
    postgresql_async_session: AsyncSession,
) -> None:
    db = postgresql_async_session
    event = _request_event()
    accepted = await accept_notification_request(db, event)

    async def unavailable(
        _delivery: NotificationDelivery,
        _request: NotificationDeliveryRequestedV1,
    ) -> str:
        raise NotificationProviderError("transport", "timeout")

    first = await deliver_due_notifications(
        db,
        unavailable,
        claim_token="consumer-a",
        retry_delay=lambda _attempt: timedelta(seconds=1),
        now=_NOW,
    )
    assert first.retried == 1

    delivery = (await db.scalars(select(NotificationDelivery))).one()
    assert delivery.next_attempt_at == _NOW + timedelta(seconds=1)

    # Make the stored retry due without needing a worker loop or broker.
    delivery.next_attempt_at = _NOW - timedelta(seconds=1)
    await db.commit()
    second = await deliver_due_notifications(
        db,
        unavailable,
        claim_token="consumer-b",
        retry_delay=lambda _attempt: timedelta(seconds=1),
        now=_NOW,
    )
    assert second.retried == 1

    delivery.next_attempt_at = _NOW - timedelta(seconds=1)
    await db.commit()
    third = await deliver_due_notifications(
        db,
        unavailable,
        claim_token="consumer-c",
        retry_delay=lambda _attempt: timedelta(seconds=1),
        now=_NOW,
    )
    assert third.dead_lettered == 1
    inbox = await db.get(InboxConsumption, accepted.inbox_id)
    assert inbox is not None
    assert inbox.status == "dead_letter"


async def test_worker_record_handoff_persists_before_an_offset_can_commit(
    postgresql_async_session: AsyncSession,
) -> None:
    db = postgresql_async_session
    event = _request_event()

    async def provider(
        _delivery: NotificationDelivery,
        _request: NotificationDeliveryRequestedV1,
    ) -> str:
        return "provider-message-1"

    await process_notification_record(
        db,
        event.model_dump_json().encode(),
        provider,
    )

    inbox = (await db.scalars(select(InboxConsumption))).one()
    delivery = (await db.scalars(select(NotificationDelivery))).one()
    assert inbox.status == "completed"
    assert delivery.status == "delivered"


def test_notification_delivery_migration_round_trip(
    apply_migrations: None,
) -> None:
    async_url = os.environ["DATABASE_URL_TEST"]
    sync_url = async_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    config = Config(str(Path(__file__).parents[5] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", sync_url.replace("%", "%%"))

    engine = sa.create_engine(sync_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO inbox_consumptions (
                        consumer_name,
                        message_id,
                        event_type,
                        payload,
                        status,
                        created_at,
                        processed_at
                    ) VALUES (
                        'migration-test',
                        'migration-message',
                        'notification.delivery_requested.v1',
                        '{}'::json,
                        'processing',
                        CURRENT_TIMESTAMP,
                        NULL
                    )
                    """
                )
            )
    finally:
        engine.dispose()

    try:
        command.downgrade(config, "b771ac41bc8f")
        downgraded_engine = sa.create_engine(sync_url)
        try:
            inspector = sa.inspect(downgraded_engine)
            assert "notification_deliveries" not in inspector.get_table_names()
            inbox_columns = {
                column["name"]: column
                for column in inspector.get_columns("inbox_consumptions")
            }
            assert "status" not in inbox_columns
            assert inbox_columns["processed_at"]["nullable"] is False
            with downgraded_engine.connect() as connection:
                processed_at = connection.scalar(
                    sa.text(
                        "SELECT processed_at FROM inbox_consumptions "
                        "WHERE message_id = 'migration-message'"
                    )
                )
            assert processed_at is not None
        finally:
            downgraded_engine.dispose()
    finally:
        command.upgrade(config, "head")
