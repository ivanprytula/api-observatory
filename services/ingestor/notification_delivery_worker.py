"""Minimal Redpanda worker for durable notification-delivery requests.

The process deliberately does not import the FastAPI application lifespan.  It
commits one broker offset only after the corresponding database transition has
committed, preserving at-least-once processing across restarts.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any, Protocol

from aiokafka import AIOKafkaConsumer, ConsumerRecord, TopicPartition
from sqlalchemy.ext.asyncio import AsyncSession

from libs.contracts.events import TOPIC_NOTIFICATION_DELIVERY_REQUESTS_V1
from services.ingestor.config import settings
from services.ingestor.database import AsyncSessionLocal
from services.ingestor.notification_delivery_consumer import (
    DeliverNotification,
    accept_notification_request,
    deliver_due_notifications,
)
from services.ingestor.notifications import deliver_notification_channel


logger = logging.getLogger(__name__)

CONSUMER_GROUP_ID = "notification-delivery-v1"
_POLL_TIMEOUT_MS = 1_000
_MAX_RECORDS_PER_POLL = 10


class NotificationBrokerConsumer(Protocol):
    """Small aiokafka seam that keeps worker behavior locally testable."""

    async def getmany(
        self,
        *,
        timeout_ms: int,
        max_records: int,
    ) -> dict[TopicPartition, list[ConsumerRecord]]: ...

    async def commit(self, offsets: dict[TopicPartition, int]) -> None: ...


type SessionFactory = Callable[[], AsyncSession]


async def process_notification_record(
    db: AsyncSession,
    value: bytes | None,
    deliver: DeliverNotification,
) -> None:
    """Persist request intake and one bounded delivery pass for a broker value."""
    raw_event = _decode_notification_request(value)
    await accept_notification_request(db, raw_event)
    await deliver_due_notifications(db, deliver, limit=1)


async def run_notification_delivery_worker(
    consumer: NotificationBrokerConsumer,
    session_factory: SessionFactory,
    deliver: DeliverNotification,
    *,
    poll_timeout_ms: int = _POLL_TIMEOUT_MS,
    max_records_per_poll: int = _MAX_RECORDS_PER_POLL,
) -> None:
    """Poll, persist, and commit each record independently until cancelled."""
    if not 1 <= poll_timeout_ms <= 60_000:
        raise ValueError("poll_timeout_ms must be between 1 and 60000")
    if not 1 <= max_records_per_poll <= 100:
        raise ValueError("max_records_per_poll must be between 1 and 100")

    while True:
        records_by_partition = await consumer.getmany(
            timeout_ms=poll_timeout_ms,
            max_records=max_records_per_poll,
        )
        for partition, records in records_by_partition.items():
            for record in records:
                async with session_factory() as db:
                    await process_notification_record(db, record.value, deliver)
                await consumer.commit({partition: record.offset + 1})
                logger.info(
                    "notification_delivery_record_committed",
                    extra={"topic": record.topic, "partition": record.partition},
                )

        async with session_factory() as db:
            await deliver_due_notifications(db, deliver, limit=max_records_per_poll)


def _decode_notification_request(value: bytes | None) -> dict[str, Any]:
    if value is None:
        raise ValueError("Notification broker value is empty.")
    try:
        decoded = json.loads(value)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Notification broker value is not valid JSON.") from exc
    if not isinstance(decoded, dict):
        raise ValueError("Notification broker value must be a JSON object.")
    return decoded


async def _run() -> None:
    if not (
        settings.notifications_enabled
        and settings.notification_delivery_mode == "broker"
        and settings.broker_enabled
    ):
        raise RuntimeError(
            "Notification worker requires notifications, broker delivery mode, "
            "and broker integration to be enabled."
        )

    consumer = AIOKafkaConsumer(
        TOPIC_NOTIFICATION_DELIVERY_REQUESTS_V1,
        bootstrap_servers=settings.broker_url,
        group_id=CONSUMER_GROUP_ID,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    try:
        await run_notification_delivery_worker(
            consumer,
            AsyncSessionLocal,
            deliver_notification_channel,
        )
    finally:
        await consumer.stop()


def main() -> None:
    """Run the notification worker as a standalone container command."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
