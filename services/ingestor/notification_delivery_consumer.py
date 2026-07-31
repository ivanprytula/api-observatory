"""Provider-neutral orchestration for durable notification delivery.

This module deliberately has no broker polling or provider configuration.  A
future broker adapter must call these functions and commit its offset only
after they return, because each outcome is committed here first.
"""

from __future__ import annotations

import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from libs.contracts.events import (
    NotificationDeliveryRequestedV1,
    NotificationErrorCategory,
)
from services.ingestor.models import InboxConsumption, NotificationDelivery
from services.ingestor.repositories.notification_delivery import (
    MAX_DELIVERY_ATTEMPTS,
    add_channel_deliveries,
    claim_due_deliveries,
    claim_notification_request,
    dead_letter_delivery,
    mark_delivery_delivered,
    schedule_delivery_retry,
)


type DeliverNotification = Callable[
    [NotificationDelivery, NotificationDeliveryRequestedV1], Awaitable[str | None]
]
type RetryDelay = Callable[[int], timedelta]

_retry_jitter = random.SystemRandom()


@dataclass(frozen=True, slots=True)
class NotificationRequestResult:
    """Durably accepted request state for a broker adapter to acknowledge."""

    inbox_id: int
    claimed: bool
    delivery_count: int


@dataclass(frozen=True, slots=True)
class NotificationDeliveryBatchResult:
    """Observable outcome of one bounded provider-delivery pass."""

    claimed: int
    delivered: int
    retried: int
    dead_lettered: int
    claim_conflicts: int


class NotificationProviderError(Exception):
    """A safe provider failure classification supplied by a channel adapter."""

    def __init__(
        self,
        category: NotificationErrorCategory,
        code: str | None = None,
        *,
        retryable: bool = True,
    ) -> None:
        super().__init__(category)
        self.category = category
        self.code = code
        self.retryable = retryable


def notification_retry_delay(attempt_count: int) -> timedelta:
    """Return the bounded retry delay after an unsuccessful delivery attempt."""
    if attempt_count == 1:
        return timedelta(seconds=_retry_jitter.randint(25, 35))
    if attempt_count == 2:
        return timedelta(seconds=_retry_jitter.randint(270, 330))
    raise ValueError("Retry delay is defined only for the first two attempts.")


def validate_notification_request(
    raw_event: NotificationDeliveryRequestedV1 | dict[str, Any],
) -> NotificationDeliveryRequestedV1:
    """Validate a versioned broker value before creating durable state."""
    if isinstance(raw_event, NotificationDeliveryRequestedV1):
        return raw_event
    try:
        return NotificationDeliveryRequestedV1.model_validate(raw_event)
    except ValidationError as exc:
        raise ValueError("Invalid notification delivery request event.") from exc


async def accept_notification_request(
    db: AsyncSession,
    raw_event: NotificationDeliveryRequestedV1 | dict[str, Any],
) -> NotificationRequestResult:
    """Validate, claim, and materialize idempotent channel delivery work."""
    event = validate_notification_request(raw_event)
    inbox, claimed = await claim_notification_request(db, event)
    if not claimed:
        return NotificationRequestResult(inbox.id, claimed=False, delivery_count=0)

    deliveries = await add_channel_deliveries(db, inbox, event)
    await db.commit()
    return NotificationRequestResult(
        inbox.id,
        claimed=True,
        delivery_count=len(deliveries),
    )


async def deliver_due_notifications(
    db: AsyncSession,
    deliver: DeliverNotification,
    *,
    limit: int = 10,
    claim_token: str | None = None,
    retry_delay: RetryDelay = notification_retry_delay,
    now: datetime | None = None,
) -> NotificationDeliveryBatchResult:
    """Process one bounded batch and persist each outcome before returning."""
    deliveries = await claim_due_deliveries(
        db,
        limit=limit,
        claim_token=claim_token,
        now=now,
    )
    delivered = retried = dead_lettered = claim_conflicts = 0

    for delivery in deliveries:
        if delivery.claim_token is None:
            raise RuntimeError("Claimed notification delivery has no claim token.")
        request = await _delivery_request(db, delivery)
        try:
            provider_reference = await deliver(delivery, request)
        except Exception as exc:
            category, code, retryable = _classify_provider_error(exc)
            if retryable and delivery.attempt_count < MAX_DELIVERY_ATTEMPTS:
                updated = await schedule_delivery_retry(
                    db,
                    delivery_id=delivery.id,
                    claim_token=delivery.claim_token,
                    next_attempt_at=delivery.last_attempt_at
                    + retry_delay(delivery.attempt_count),
                    error_category=category,
                    error_code=code,
                    error_detail=_safe_error_detail(exc),
                )
                if updated is None:
                    claim_conflicts += 1
                else:
                    retried += 1
                continue

            updated = await dead_letter_delivery(
                db,
                delivery_id=delivery.id,
                claim_token=delivery.claim_token,
                error_category=category,
                error_code=code,
                error_detail=_safe_error_detail(exc),
                now=now,
            )
            if updated is None:
                claim_conflicts += 1
            else:
                dead_lettered += 1
            continue

        updated = await mark_delivery_delivered(
            db,
            delivery_id=delivery.id,
            claim_token=delivery.claim_token,
            provider_reference=provider_reference,
            now=now,
        )
        if updated is None:
            claim_conflicts += 1
        else:
            delivered += 1

    return NotificationDeliveryBatchResult(
        claimed=len(deliveries),
        delivered=delivered,
        retried=retried,
        dead_lettered=dead_lettered,
        claim_conflicts=claim_conflicts,
    )


def _classify_provider_error(
    exc: Exception,
) -> tuple[NotificationErrorCategory, str | None, bool]:
    if isinstance(exc, NotificationProviderError):
        return exc.category, exc.code, exc.retryable
    if isinstance(exc, ValueError):
        return "configuration", type(exc).__name__, False
    return "unknown", type(exc).__name__, True


def _safe_error_detail(exc: Exception) -> str:
    """Avoid persisting provider responses, destinations, or credentials."""
    return f"{type(exc).__name__}: notification provider call failed"


async def _delivery_request(
    db: AsyncSession,
    delivery: NotificationDelivery,
) -> NotificationDeliveryRequestedV1:
    inbox = await db.get(InboxConsumption, delivery.inbox_consumption_id)
    if inbox is None:
        raise RuntimeError(
            f"Inbox consumption {delivery.inbox_consumption_id} is missing."
        )
    return validate_notification_request(inbox.payload)
