"""Integration coverage for minimal Outbox/Inbox baseline (step 6.2)."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.repositories import messaging


pytestmark = pytest.mark.integration


@pytest.mark.postgresonly
async def test_outbox_enqueue_and_inbox_idempotent_consumption(
    postgresql_async_session: AsyncSession,
) -> None:
    """Verify outbox insert works and inbox deduplicates duplicate message IDs."""
    outbox_event = await messaging.enqueue_outbox_event(
        postgresql_async_session,
        aggregate_type="observation",
        aggregate_id="observation-42",
        event_type="observation.created",
        payload={"observation_id": 42},
        idempotency_key="outbox-observation-42-created",
        tenant_id=101,
    )
    assert outbox_event.id is not None

    pending = await messaging.list_pending_outbox_events(
        postgresql_async_session,
        limit=10,
    )
    assert any(event.id == outbox_event.id for event in pending), pending

    first_insert = await messaging.try_observation_inbox_consumption(
        postgresql_async_session,
        consumer_name="analytics-projection",
        message_id="msg-001",
        event_type="observation.created",
        payload={"observation_id": 42},
    )
    second_insert = await messaging.try_observation_inbox_consumption(
        postgresql_async_session,
        consumer_name="analytics-projection",
        message_id="msg-001",
        event_type="observation.created",
        payload={"observation_id": 42},
    )

    assert first_insert is True
    assert second_insert is False

    count_result = await postgresql_async_session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM inbox_consumptions
            WHERE consumer_name = :consumer_name
              AND message_id = :message_id
            """
        ),
        {
            "consumer_name": "analytics-projection",
            "message_id": "msg-001",
        },
    )
    assert count_result.scalar_one() == 1


@pytest.mark.postgresonly
async def test_outbox_claim_failure_retry_and_publish_lifecycle(
    postgresql_async_session: AsyncSession,
) -> None:
    """Verify claim/fail/retry/publish transitions for one outbox event."""
    event = await messaging.enqueue_outbox_event(
        postgresql_async_session,
        aggregate_type="subscription",
        aggregate_id="sub-7",
        event_type="subscription.delivery_requested",
        payload={"subscription_id": 7},
        idempotency_key="outbox-sub-7-delivery-requested",
    )

    claimed = await messaging.claim_pending_outbox_events(
        postgresql_async_session,
        limit=10,
    )
    assert len(claimed) >= 1
    claimed_event = next(item for item in claimed if item.id == event.id)
    assert claimed_event.publish_attempts == 1

    failed = await messaging.mark_outbox_publish_failed(
        postgresql_async_session,
        event_id=event.id,
        error_message="broker timeout",
    )
    assert failed is not None
    assert failed.published_at is None
    assert failed.last_error == "broker timeout"

    claimed_retry = await messaging.claim_pending_outbox_events(
        postgresql_async_session,
        limit=10,
    )
    retry_event = next(item for item in claimed_retry if item.id == event.id)
    assert retry_event.publish_attempts == 2

    published = await messaging.mark_outbox_published(
        postgresql_async_session,
        event_id=event.id,
    )
    assert published is not None
    assert published.published_at is not None
    assert published.last_error is None

    pending_after_publish = await messaging.list_pending_outbox_events(
        postgresql_async_session,
        limit=10,
    )
    assert all(item.id != event.id for item in pending_after_publish), (
        pending_after_publish
    )
