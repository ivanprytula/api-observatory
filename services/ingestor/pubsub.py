"""Redis Pub/Sub bridge — ingestor-side publisher and subscriber.

Provides a thin async pub/sub layer on top of the existing Redis connection.
Used for two purposes:

1. **Publishing** (ingestor → Redis) — called by ``events.py`` and ``jobs.py``
   whenever a significant event occurs:
   - ``type: observation.created`` — after a successful DB write
   - ``type: job.progress``  — from priority-queue job execution steps

2. **Subscribing** (Redis → FastAPI WS) — the WebSocket router subscribes to
   the shared channel and fans messages out to connected browser clients.

Architecture:

    Ingestor write / Celery task
       │
       ├─► Kafka topic (existing, async events system)
       │
       └─► Redis PUBLISH  "ingestor:events"
                │
                ├─► FastAPI WS /ws/observations/stream  → Browser
                │
                └─► Django Channels bridge task    → portal WS → Browser

Channel name: ``ingestor:events``  (one channel, multiplexed by ``type`` field).

Message envelope (JSON-serialised):

    {"type": "observation.created", "observation_id": 1, "source": "...", "ts": "..."}
    {"type": "job.progress",   "job_id": "...", "status": "running",
     "progress": 0.4, "message": "Batch 2/5 complete"}

Fail-open: if Redis is not configured or unavailable, publish() logs a warning
and returns without raising, keeping the write path non-blocking.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

from services.ingestor.config import settings


logger = logging.getLogger(__name__)

# Shared channel name — both services subscribe/publish to this key
PUBSUB_CHANNEL = "ingestor:events"

# Module-level Redis client dedicated to pub/sub.
# A *separate* connection is required because a Redis connection in SUBSCRIBE
# mode can only run pub/sub commands — it cannot be shared with cache reads.
_pubsub_client: Redis | None = None


# ---------------------------------------------------------------------------
# Lifecycle — wired by services_lifecycle.py
# ---------------------------------------------------------------------------


async def connect_pubsub(redis_url: str) -> None:
    """Create the dedicated pub/sub Redis connection.

    Args:
        redis_url: Redis connection URL (e.g. ``redis://localhost:6379/0``).
    """
    global _pubsub_client
    _pubsub_client = Redis.from_url(redis_url, decode_responses=True)
    await _pubsub_client.ping()  # ty: ignore[invalid-await]
    logger.info("pubsub_connected", extra={"url": redis_url})


async def disconnect_pubsub() -> None:
    """Close the pub/sub Redis connection gracefully."""
    global _pubsub_client
    if _pubsub_client is not None:
        await _pubsub_client.aclose()
        _pubsub_client = None
        logger.info("pubsub_disconnected")


# ---------------------------------------------------------------------------
# Publisher
# ---------------------------------------------------------------------------


async def publish_event(event_type: str, payload: dict[str, Any]) -> None:
    """Publish a typed event to ``ingestor:events``.

    Fail-open: logs a warning and returns without raising if Redis is not
    available.  The write path (DB insert, Kafka) must not be blocked by a
    pub/sub failure.

    Args:
        event_type: Discriminator string — ``"observation.created"`` or
            ``"job.progress"``.  Clients use this field to route messages.
        payload:    Event-specific fields merged into the envelope.
    """
    if _pubsub_client is None:
        logger.debug("pubsub_skip_not_connected", extra={"type": event_type})
        return

    envelope: dict[str, Any] = {
        "type": event_type,
        "ts": datetime.now(UTC).isoformat(),
        **payload,
    }
    try:
        await _pubsub_client.publish(PUBSUB_CHANNEL, json.dumps(envelope))
        logger.debug("pubsub_published", extra={"type": event_type})
    except Exception as exc:
        logger.warning(
            "pubsub_publish_error",
            extra={"type": event_type, "error": str(exc)},
        )


async def publish_observation_created(observation_id: int, source: str) -> None:
    """Convenience wrapper — publish a ``observation.created`` event.

    Args:
        observation_id: Primary key of the newly created observation.
        source:    Source identifier for the observation.
    """
    await publish_event(
        "observation.created",
        {"observation_id": observation_id, "source": source},
    )


async def publish_job_progress(
    job_id: str,
    status: str,
    progress: float,
    message: str = "",
) -> None:
    """Convenience wrapper — publish a ``job.progress`` event.

    Args:
        job_id:   Unique identifier for the running job.
        status:   Current status string (``"running"``, ``"complete"``,
                  ``"error"``).
        progress: Fraction complete in ``[0.0, 1.0]``.
        message:  Optional human-readable progress description.
    """
    await publish_event(
        "job.progress",
        {
            "job_id": job_id,
            "status": status,
            "progress": round(progress, 4),
            "message": message,
        },
    )


async def publish_drift_event(
    source_id: int,
    drift_event_id: int,
    event_type: str,
    severity: str,
    compatibility_score: float,
) -> None:
    """Publish a ``drift.detected`` notification after a DriftEvent is persisted.

    Clients listening on the WebSocket stream receive this immediately after
    the DB write, without polling.

    Args:
        source_id:          ID of the SourceProfile that drifted.
        drift_event_id:     Primary key of the newly created DriftEvent.
        event_type:         ``"breaking"`` or ``"non_breaking"``.
        severity:           Severity label (``"low"``/``"medium"``/``"high"``/
                            ``"critical"``).
        compatibility_score: Score in ``[0.0, 100.0]``.
    """
    await publish_event(
        "drift.detected",
        {
            "source_id": source_id,
            "drift_event_id": drift_event_id,
            "event_type": event_type,
            "severity": severity,
            "compatibility_score": round(compatibility_score, 4),
        },
    )


# ---------------------------------------------------------------------------
# Subscriber (used by FastAPI WS endpoint)
# ---------------------------------------------------------------------------


async def subscribe_events() -> AsyncGenerator[dict[str, Any]]:
    """Async generator that yields parsed event envelopes from ``ingestor:events``.

    Creates a *short-lived* subscriber connection to avoid blocking the shared
    pub/sub client.  Yields decoded ``dict`` envelopes until the caller
    exhausts or closes the generator.

    The generator is designed to be consumed inside a single WebSocket handler
    coroutine — each connected client gets its own subscriber::

        async for event in subscribe_events():
            await ws.send_json(event)

    Yields:
        Parsed event envelope dict, e.g.
        ``{"type": "observation.created", "observation_id": 1, ...}``.

    Note:
        If Redis is not configured (``settings.redis_enabled`` is False) the
        generator yields nothing and returns immediately so that the WS
        handler can fall back gracefully.
    """
    if not settings.redis_enabled:
        logger.debug("pubsub_subscribe_skip_disabled")
        return

    # Create a fresh connection for this subscriber — pub/sub connections must
    # not be shared with regular command connections.
    client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
    pubsub = client.pubsub()

    try:
        await pubsub.subscribe(PUBSUB_CHANNEL)
        logger.debug("pubsub_subscribed", extra={"channel": PUBSUB_CHANNEL})

        async for raw in pubsub.listen():
            if raw["type"] != "message":
                continue  # skip subscribe-confirmation messages
            try:
                yield json.loads(raw["data"])
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning("pubsub_decode_error", extra={"error": str(exc)})
    finally:
        await pubsub.unsubscribe(PUBSUB_CHANNEL)
        await pubsub.aclose()
        await client.aclose()
        logger.debug("pubsub_unsubscribed", extra={"channel": PUBSUB_CHANNEL})
