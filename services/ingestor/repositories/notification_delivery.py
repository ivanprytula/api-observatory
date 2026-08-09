"""Durable inbox and per-channel notification delivery state transitions."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import cast
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from libs.contracts.events import (
    EVENT_NOTIFICATION_DELIVERY_DEAD_LETTERED_V1,
    NotificationChannel,
    NotificationDeliveryDeadLetteredPayloadV1,
    NotificationDeliveryDeadLetteredV1,
    NotificationDeliveryRequestedV1,
    NotificationErrorCategory,
)
from services.ingestor.core.utils import _aware_utc
from services.ingestor.models import (
    InboxConsumption,
    NotificationDelivery,
    OutboxEvent,
    _utcnow,
)
from services.ingestor.repositories.messaging import add_outbox_event


CONSUMER_NAME = "notification-delivery-v1"
MAX_DELIVERY_ATTEMPTS = 3
_INBOX_TERMINAL_STATUSES = {
    "completed",
    "completed_with_dead_letters",
    "dead_letter",
}
_DELIVERY_TERMINAL_STATUSES = {"delivered", "dead_letter"}


async def claim_notification_request(
    db: AsyncSession,
    event: NotificationDeliveryRequestedV1,
    *,
    lease_seconds: int = 30,
    now: datetime | None = None,
) -> tuple[InboxConsumption, bool]:
    """Claim one message, reclaiming it only after an expired processing lease."""
    current_time = now or _utcnow()
    lease_expires_at = current_time + timedelta(seconds=lease_seconds)
    event_payload = event.model_dump(mode="json")
    statement = (
        insert(InboxConsumption)
        .values(
            consumer_name=CONSUMER_NAME,
            message_id=event.message_id,
            event_type=event.event_type,
            payload=event_payload,
            status="processing",
            lease_expires_at=lease_expires_at,
            processed_at=None,
        )
        .on_conflict_do_nothing(index_elements=["consumer_name", "message_id"])
        .returning(InboxConsumption)
    )
    inbox = await db.scalar(statement)
    if inbox is not None:
        await db.commit()
        await db.refresh(inbox)
        return inbox, True

    inbox = await db.scalar(
        select(InboxConsumption)
        .where(
            InboxConsumption.consumer_name == CONSUMER_NAME,
            InboxConsumption.message_id == event.message_id,
        )
        .with_for_update()
    )
    if inbox is None:
        raise RuntimeError("Inbox conflict did not return an existing row.")
    if inbox.status in _INBOX_TERMINAL_STATUSES:
        await db.commit()
        return inbox, False
    if inbox.lease_expires_at is not None and inbox.lease_expires_at > current_time:
        await db.commit()
        return inbox, False

    inbox.status = "processing"
    inbox.lease_expires_at = lease_expires_at
    inbox.event_type = event.event_type
    inbox.payload = event_payload
    inbox.processed_at = None
    inbox.last_error_category = None
    inbox.last_error_code = None
    inbox.last_error_detail = None
    await db.commit()
    await db.refresh(inbox)
    return inbox, True


async def add_channel_deliveries(
    db: AsyncSession,
    inbox: InboxConsumption,
    event: NotificationDeliveryRequestedV1,
) -> list[NotificationDelivery]:
    """Create one idempotent pending delivery per requested channel."""
    payload = event.payload
    for channel in payload.channels:
        await db.execute(
            insert(NotificationDelivery)
            .values(
                inbox_consumption_id=inbox.id,
                message_id=event.message_id,
                incident_id=payload.incident_id,
                source_id=payload.source_id,
                tenant_id=payload.tenant_id,
                event_type=event.event_type,
                severity=payload.severity,
                channel=channel,
                status="pending",
                attempt_count=0,
            )
            .on_conflict_do_nothing(index_elements=["message_id", "channel"])
        )
    await db.flush()
    deliveries = await db.scalars(
        select(NotificationDelivery)
        .where(NotificationDelivery.message_id == event.message_id)
        .order_by(NotificationDelivery.channel)
    )
    return list(deliveries)


async def claim_due_deliveries(
    db: AsyncSession,
    *,
    limit: int = 100,
    claim_token: str | None = None,
    lease_seconds: int = 30,
    now: datetime | None = None,
) -> list[NotificationDelivery]:
    """Claim due channel work in a bounded, multi-worker-safe batch."""
    current_time = now or _utcnow()
    token = claim_token or str(uuid4())
    due_unclaimed_work = and_(
        NotificationDelivery.attempt_count < MAX_DELIVERY_ATTEMPTS,
        or_(
            NotificationDelivery.status == "pending",
            and_(
                NotificationDelivery.status == "retry_scheduled",
                NotificationDelivery.next_attempt_at <= current_time,
            ),
        ),
        or_(
            NotificationDelivery.lease_expires_at.is_(None),
            NotificationDelivery.lease_expires_at <= current_time,
        ),
    )
    abandoned_work = and_(
        NotificationDelivery.status == "processing",
        NotificationDelivery.lease_expires_at.is_not(None),
        NotificationDelivery.lease_expires_at <= current_time,
    )
    statement = (
        select(NotificationDelivery)
        .where(
            NotificationDelivery.deleted_at.is_(None),
            or_(due_unclaimed_work, abandoned_work),
        )
        .order_by(NotificationDelivery.id)
        .with_for_update(skip_locked=True)
        .limit(limit)
    )
    deliveries = list((await db.scalars(statement)).all())
    for delivery in deliveries:
        is_abandoned_attempt = delivery.status == "processing"
        delivery.status = "processing"
        if not is_abandoned_attempt:
            delivery.attempt_count += 1
        delivery.claim_token = token
        delivery.lease_expires_at = current_time + timedelta(seconds=lease_seconds)
        delivery.next_attempt_at = None
        delivery.first_attempt_at = delivery.first_attempt_at or current_time
        delivery.last_attempt_at = current_time
    await db.commit()
    return deliveries


async def mark_delivery_delivered(
    db: AsyncSession,
    *,
    delivery_id: int,
    claim_token: str,
    provider_reference: str | None = None,
    now: datetime | None = None,
) -> NotificationDelivery | None:
    """Persist successful provider delivery for the current lease owner."""
    current_time = now or _utcnow()
    delivery = await _get_claimed_delivery(db, delivery_id, claim_token)
    if delivery is None:
        return None
    delivery.status = "delivered"
    delivery.delivered_at = current_time
    delivery.next_attempt_at = None
    delivery.provider_reference = (
        provider_reference[:255] if provider_reference is not None else None
    )
    _clear_delivery_claim(delivery)
    _clear_delivery_error(delivery)
    await _refresh_inbox_status(db, delivery.inbox_consumption_id, current_time)
    await db.commit()
    await db.refresh(delivery)
    return delivery


async def schedule_delivery_retry(
    db: AsyncSession,
    *,
    delivery_id: int,
    claim_token: str,
    next_attempt_at: datetime,
    error_category: NotificationErrorCategory,
    error_code: str | None,
    error_detail: str,
) -> NotificationDelivery | None:
    """Persist a retry only while the bounded attempt budget remains."""
    delivery = await _get_claimed_delivery(db, delivery_id, claim_token)
    if delivery is None:
        return None
    if delivery.attempt_count >= MAX_DELIVERY_ATTEMPTS:
        raise ValueError("Delivery attempt budget is exhausted.")
    delivery.status = "retry_scheduled"
    delivery.next_attempt_at = next_attempt_at
    _clear_delivery_claim(delivery)
    _set_delivery_error(delivery, error_category, error_code, error_detail)
    await db.commit()
    await db.refresh(delivery)
    return delivery


async def dead_letter_delivery(
    db: AsyncSession,
    *,
    delivery_id: int,
    claim_token: str,
    error_category: NotificationErrorCategory,
    error_code: str | None,
    error_detail: str,
    now: datetime | None = None,
) -> tuple[NotificationDelivery, OutboxEvent] | None:
    """Atomically persist terminal state and its sanitized DLQ outbox intent."""
    current_time = now or _utcnow()
    delivery = await _get_claimed_delivery(db, delivery_id, claim_token)
    if delivery is None:
        return None
    delivery.status = "dead_letter"
    delivery.dead_lettered_at = current_time
    delivery.next_attempt_at = None
    first_attempt_at = delivery.first_attempt_at or current_time
    last_attempt_at = delivery.last_attempt_at or current_time
    delivery.first_attempt_at = first_attempt_at
    delivery.last_attempt_at = last_attempt_at
    _clear_delivery_claim(delivery)
    _set_delivery_error(delivery, error_category, error_code, error_detail)

    dlq_message_id = f"notification-delivery-dlq:{delivery.id}"
    event = NotificationDeliveryDeadLetteredV1(
        message_id=dlq_message_id,
        occurred_at=_aware_utc(current_time),
        payload=NotificationDeliveryDeadLetteredPayloadV1(
            delivery_id=delivery.id,
            request_message_id=delivery.message_id,
            incident_id=delivery.incident_id,
            source_id=delivery.source_id,
            tenant_id=delivery.tenant_id,
            channel=cast("NotificationChannel", delivery.channel),
            attempt_count=delivery.attempt_count,
            error_category=error_category,
            error_code=error_code[:64] if error_code is not None else None,
            first_attempt_at=_aware_utc(first_attempt_at),
            last_attempt_at=_aware_utc(last_attempt_at),
        ),
    )
    outbox = await add_outbox_event(
        db,
        aggregate_type="notification_delivery",
        aggregate_id=str(delivery.id),
        event_type=EVENT_NOTIFICATION_DELIVERY_DEAD_LETTERED_V1,
        payload=event.model_dump(mode="json"),
        idempotency_key=dlq_message_id,
        tenant_id=delivery.tenant_id,
    )
    await _refresh_inbox_status(db, delivery.inbox_consumption_id, current_time)
    await db.commit()
    await db.refresh(delivery)
    await db.refresh(outbox)
    return delivery, outbox


async def _get_claimed_delivery(
    db: AsyncSession,
    delivery_id: int,
    claim_token: str,
) -> NotificationDelivery | None:
    return await db.scalar(
        select(NotificationDelivery)
        .where(
            NotificationDelivery.id == delivery_id,
            NotificationDelivery.status == "processing",
            NotificationDelivery.claim_token == claim_token,
        )
        .with_for_update()
    )


def _clear_delivery_claim(delivery: NotificationDelivery) -> None:
    delivery.claim_token = None
    delivery.lease_expires_at = None


def _clear_delivery_error(delivery: NotificationDelivery) -> None:
    delivery.last_error_category = None
    delivery.last_error_code = None
    delivery.last_error_detail = None


def _set_delivery_error(
    delivery: NotificationDelivery,
    category: NotificationErrorCategory,
    code: str | None,
    detail: str,
) -> None:
    delivery.last_error_category = category
    delivery.last_error_code = code[:64] if code is not None else None
    delivery.last_error_detail = detail[:512]


async def _refresh_inbox_status(
    db: AsyncSession,
    inbox_id: int,
    current_time: datetime,
) -> None:
    await db.flush()
    inbox = await db.get(InboxConsumption, inbox_id)
    if inbox is None:
        raise RuntimeError(f"Inbox consumption {inbox_id} is missing.")
    statuses = list(
        (
            await db.scalars(
                select(NotificationDelivery.status).where(
                    NotificationDelivery.inbox_consumption_id == inbox_id,
                    NotificationDelivery.deleted_at.is_(None),
                )
            )
        ).all()
    )
    if not statuses or not all(
        status in _DELIVERY_TERMINAL_STATUSES for status in statuses
    ):
        inbox.status = "processing"
        return
    if all(status == "delivered" for status in statuses):
        inbox.status = "completed"
    elif all(status == "dead_letter" for status in statuses):
        inbox.status = "dead_letter"
    else:
        inbox.status = "completed_with_dead_letters"
    inbox.lease_expires_at = None
    inbox.processed_at = current_time
