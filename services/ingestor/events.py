"""Async Kafka event producer — fail-open on connection errors.

Modeled on app/cache.py singleton pattern:
- Module-level _producer singleton
- connect_producer() / disconnect_producer() for lifespan wiring
- All operations are pure async, fail-open on KafkaError

Advanced Python patterns demonstrated:
- TypeVar + Generic: EventPayload[T] typed event envelope (Phase 1 spec)
- Observer pattern: publish_record_created called from records router
  after successful DB write (record creation triggers the event)
- Circuit breaker (Phase 4): _send_to_kafka is wrapped with @circuit_breaker
  so repeated Kafka failures open the circuit and stop hammering the broker
"""

from __future__ import annotations

import json
import logging
from typing import Any

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from libs.contracts.events import (
    EVENT_DOC_SCRAPED,
    EVENT_RECORD_CREATED,
    TOPIC_RECORD_CREATED,
    TOPIC_SCRAPED,
    DocScrapedPayload,
    EventPayload,
    RecordCreatedPayload,
)
from libs.platform.circuit_breaker import CircuitOpenError, circuit_breaker
from services.ingestor import pubsub as _pubsub


# ---------------------------------------------------------------------------
# Module-level singleton (initialized in lifespan startup)
# ---------------------------------------------------------------------------
_producer: AIOKafkaProducer | None = None

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal send helper (circuit-breaker guarded)
# ---------------------------------------------------------------------------
@circuit_breaker(failure_threshold=5, recovery_timeout=30)
async def _send_to_kafka(topic: str, value: bytes) -> None:
    """Low-level send — raises on failure so the circuit breaker can track it.

    Args:
        topic: Kafka topic name.
        value: Serialized message bytes.

    Raises:
        KafkaError: If the broker rejects or is unreachable.
        RuntimeError: If the producer is not connected.
    """
    if _producer is None:
        return
    await _producer.send_and_wait(topic, value=value)


# ---------------------------------------------------------------------------
# Lifecycle helpers (called from app/main.py lifespan)
# ---------------------------------------------------------------------------
async def connect_producer(bootstrap_servers: str) -> None:
    """Initialize and start the Kafka producer.

    Args:
        bootstrap_servers: Comma-separated Kafka bootstrap brokers.

    Raises:
        KafkaError: If broker is unreachable (propagated to caller for logging).
    """
    global _producer
    _producer = AIOKafkaProducer(bootstrap_servers=bootstrap_servers)
    assert _producer is not None  # type safety check
    await _producer.start()
    logger.info("kafka_producer_connected", extra={"servers": bootstrap_servers})


async def disconnect_producer() -> None:
    """Stop and clean up the Kafka producer."""
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None
    logger.info("kafka_producer_disconnected")


# ---------------------------------------------------------------------------
# Publisher
# ---------------------------------------------------------------------------
async def publish_record_created(record_id: int, payload: dict[str, Any]) -> None:
    """Publish a record.created event to TOPIC_RECORD_CREATED.

    Fail-open: KafkaError and CircuitOpenError are logged as warnings; the
    request is never failed. No-op if producer is not connected.

    Args:
        record_id: Primary key of the newly created record.
        payload: Additional record fields to include in the event.
    """
    if _producer is None:
        return

    event_payload: RecordCreatedPayload = {"record_id": record_id, **payload}
    event: EventPayload[RecordCreatedPayload] = EventPayload(
        event_type=EVENT_RECORD_CREATED,
        payload=event_payload,
    )

    try:
        await _send_to_kafka(
            TOPIC_RECORD_CREATED,
            json.dumps(event.to_dict()).encode(),
        )
        logger.debug(
            "event_published",
            extra={"event_type": EVENT_RECORD_CREATED, "record_id": record_id},
        )
    except (KafkaError, CircuitOpenError) as exc:
        logger.warning(
            "kafka_publish_failed",
            extra={"error": str(exc), "record_id": record_id},
        )
    # Also publish to Redis Pub/Sub so the FastAPI WS endpoint and
    # the Django Channels bridge can stream the event in real time.
    source = payload.get("source", "")
    await _pubsub.publish_record_created(record_id, source)


async def publish_doc_scraped(source: str, count: int) -> None:
    """Publish a doc.scraped event to TOPIC_SCRAPED.

    Fail-open: KafkaError and CircuitOpenError are logged as warnings; the
    request is never failed. No-op if the producer is not connected.

    Args:
        source: Scraper source identifier (e.g., 'hn', 'jsonplaceholder').
        count: Number of documents scraped and stored.
    """
    if _producer is None:
        return

    event_payload: DocScrapedPayload = {"source": source, "count": count}
    event: EventPayload[DocScrapedPayload] = EventPayload(
        event_type=EVENT_DOC_SCRAPED,
        payload=event_payload,
    )

    try:
        await _send_to_kafka(
            TOPIC_SCRAPED,
            json.dumps(event.to_dict()).encode(),
        )
        logger.debug(
            "event_published",
            extra={"event_type": EVENT_DOC_SCRAPED, "source": source, "count": count},
        )
    except (KafkaError, CircuitOpenError) as exc:
        logger.warning(
            "kafka_publish_failed",
            extra={"error": str(exc), "source": source},
        )
