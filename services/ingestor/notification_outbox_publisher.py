"""Bounded notification outbox publishing and its ingestor-owned runtime loop."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from libs.contracts.events import (
    EVENT_NOTIFICATION_DELIVERY_DEAD_LETTERED_V1,
    EVENT_NOTIFICATION_DELIVERY_REQUESTED_V1,
    TOPIC_NOTIFICATION_DELIVERY_DLQ_V1,
    TOPIC_NOTIFICATION_DELIVERY_REQUESTS_V1,
)
from services.ingestor.config import settings
from services.ingestor.models import _utcnow
from services.ingestor.repositories.messaging import (
    claim_pending_outbox_events,
    mark_outbox_publish_failed,
    mark_outbox_published,
)


type PublishBytes = Callable[[str, bytes], Awaitable[None]]
type SessionFactory = Callable[[], AsyncSession]

logger = logging.getLogger(__name__)

_NOTIFICATION_TOPICS = {
    EVENT_NOTIFICATION_DELIVERY_REQUESTED_V1: (TOPIC_NOTIFICATION_DELIVERY_REQUESTS_V1),
    EVENT_NOTIFICATION_DELIVERY_DEAD_LETTERED_V1: TOPIC_NOTIFICATION_DELIVERY_DLQ_V1,
}
_OUTBOX_EVENT_TYPES = tuple(_NOTIFICATION_TOPICS)
_RETRY_BASE_SECONDS = 5
_RETRY_MAX_SECONDS = 300
_MAX_BATCH_SIZE = 100


@dataclass(frozen=True, slots=True)
class OutboxPublishBatchResult:
    """Observable outcome of one bounded publisher pass."""

    claimed: int
    published: int
    failed: int
    claim_conflicts: int


def notification_outbox_publisher_enabled() -> bool:
    """Return whether the ingestor should own the notification publisher loop."""
    return (
        settings.notifications_enabled
        and settings.notification_delivery_mode == "broker"
        and settings.broker_enabled
    )


def notification_outbox_topic(event_type: str) -> str:
    """Resolve a supported notification event to its versioned Redpanda topic."""
    try:
        return _NOTIFICATION_TOPICS[event_type]
    except KeyError:
        raise ValueError(
            f"Unsupported notification outbox event: {event_type}"
        ) from None


def serialize_outbox_payload(payload: dict) -> bytes:
    """Serialize one JSON outbox envelope deterministically."""
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def outbox_retry_delay_seconds(publish_attempts: int) -> int:
    """Return capped exponential backoff for the completed publish attempt."""
    if publish_attempts < 1:
        raise ValueError("publish_attempts must be at least one")
    exponent = min(publish_attempts - 1, 30)
    return min(_RETRY_BASE_SECONDS * (2**exponent), _RETRY_MAX_SECONDS)


async def publish_notification_outbox_batch(
    db: AsyncSession,
    publish: PublishBytes,
    *,
    limit: int = 10,
    lease_seconds: int = 120,
    publish_timeout_seconds: float = 10,
    now: datetime | None = None,
) -> OutboxPublishBatchResult:
    """Publish one bounded notification-only batch and persist every outcome."""
    if not 1 <= limit <= _MAX_BATCH_SIZE:
        raise ValueError(f"limit must be between 1 and {_MAX_BATCH_SIZE}")
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be positive")
    if not 0 < publish_timeout_seconds <= 60:
        raise ValueError("publish_timeout_seconds must be between 0 and 60")

    current_time = now or _utcnow()
    claim_token = str(uuid4())
    events = await claim_pending_outbox_events(
        db,
        limit=limit,
        claim_token=claim_token,
        lease_seconds=lease_seconds,
        now=current_time,
        event_types=_OUTBOX_EVENT_TYPES,
    )
    published = 0
    failed = 0
    claim_conflicts = 0

    for event in events:
        try:
            topic = notification_outbox_topic(event.event_type)
            value = serialize_outbox_payload(event.payload)
            async with asyncio.timeout(publish_timeout_seconds):
                await publish(topic, value)
        except Exception as exc:
            failed += 1
            retry_at = current_time + timedelta(
                seconds=outbox_retry_delay_seconds(event.publish_attempts)
            )
            updated = await mark_outbox_publish_failed(
                db,
                event_id=event.id,
                claim_token=claim_token,
                error_message=f"{type(exc).__name__}: publish failed",
                next_attempt_at=retry_at,
            )
            if updated is None:
                claim_conflicts += 1
            continue

        updated = await mark_outbox_published(
            db,
            event_id=event.id,
            claim_token=claim_token,
            published_at=current_time,
        )
        if updated is None:
            claim_conflicts += 1
        else:
            published += 1

    return OutboxPublishBatchResult(
        claimed=len(events),
        published=published,
        failed=failed,
        claim_conflicts=claim_conflicts,
    )


async def run_notification_outbox_publisher(
    session_factory: SessionFactory,
    publish: PublishBytes,
    *,
    poll_interval_seconds: float = 1,
    batch_limit: int = 10,
    lease_seconds: int = 120,
    publish_timeout_seconds: float = 10,
) -> None:
    """Run cancellable bounded passes; isolate transient batch failures."""
    if not 0 < poll_interval_seconds <= 60:
        raise ValueError("poll_interval_seconds must be between 0 and 60")

    while True:
        try:
            async with session_factory() as db:
                result = await publish_notification_outbox_batch(
                    db,
                    publish,
                    limit=batch_limit,
                    lease_seconds=lease_seconds,
                    publish_timeout_seconds=publish_timeout_seconds,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "notification_outbox_batch_failed",
                extra={"error_type": type(exc).__name__},
            )
        else:
            if result.claimed:
                logger.info(
                    "notification_outbox_batch_complete",
                    extra={
                        "claimed": result.claimed,
                        "published": result.published,
                        "failed": result.failed,
                        "claim_conflicts": result.claim_conflicts,
                    },
                )
        await asyncio.sleep(poll_interval_seconds)
