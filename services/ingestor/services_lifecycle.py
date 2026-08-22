"""Resource initialization and lifespan management for external services.

Encapsulates startup/shutdown logic for:
- Cache (optional)
- Kafka producer (optional)

Design principle: Each service is independently initializable and gracefully
degrades if unavailable (fail-open for optional services).
"""

from __future__ import annotations

import logging
from importlib import import_module

from services.ingestor.core.config import settings
from services.ingestor.core.utils import redact_url_password


logger = logging.getLogger(__name__)


def _get_module(name: str):
    try:
        return import_module(name)
    except ImportError:
        return None


def _cache():
    return _get_module("services.ingestor.cache")


def _events():
    return _get_module("services.ingestor.events")


def _pubsub():
    return _get_module("services.ingestor.pubsub")


async def initialize_external_services() -> None:
    """Initialize all optional external services during app startup.

    Services are initialized in order of dependency:
    1. Cache (for caching)
    2. Broker (for events)

    Each service failure is logged but non-fatal (fail-open).
    """

    # Initialize cache backend (optional)
    if settings.cache_enabled:
        try:
            cache = _cache()
            if cache is not None:
                await cache.connect_cache(settings.cache_url)
                logger.info(
                    "cache_connected",
                    extra={
                        "service": "cache",
                        "url": redact_url_password(settings.cache_url),
                    },
                )
                # Phase 13.4: Warm list cache for top N sources
                await _warm_list_cache()
        except Exception as e:
            logger.warning(
                "cache_connection_failed",
                extra={"service": "cache", "error": str(e)},
            )
            # Non-fatal: cache is optional, app continues without it

    # Initialize Cache Pub/Sub (separate connection from cache, optional)
    if settings.cache_enabled:
        try:
            pubsub = _pubsub()
            if pubsub is not None:
                await pubsub.connect_pubsub(settings.cache_url)
                logger.info(
                    "pubsub_connected",
                    extra={
                        "service": "cache-pubsub",
                        "url": redact_url_password(settings.cache_url),
                    },
                )
        except Exception as e:
            logger.warning(
                "pubsub_connection_failed",
                extra={"service": "cache-pubsub", "error": str(e)},
            )

    # Initialize event broker producer (optional)
    if settings.broker_enabled:
        try:
            events = _events()
            if events is not None:
                await events.connect_producer(settings.broker_url)
                logger.info(
                    "events_producer_connected",
                    extra={
                        "service": "broker",
                        "broker": redact_url_password(settings.broker_url),
                    },
                )
        except Exception as e:
            logger.warning(
                "events_producer_connection_failed",
                extra={"service": "broker", "error": str(e)},
            )
            # Non-fatal: events are fail-open, app continues without broker


async def _warm_list_cache() -> None:
    """Pre-warm the list cache for the top N most active sources.

    Executes on startup (after Cache connects) to reduce cold-start latency.
    Fails open — any error is logged but does not prevent startup.
    """
    try:
        from sqlalchemy import func, select, text

        from services.ingestor.cache import set_observations_list
        from services.ingestor.constants import (
            CACHE_WARM_TOP_N_SOURCES,
            DEFAULT_PAGE_SIZE,
        )
        from services.ingestor.core.database import AsyncSessionLocal
        from services.ingestor.models import Observation

        async with AsyncSessionLocal() as session:
            stmt = (
                select(Observation.source_id, func.count(Observation.id).label("cnt"))
                .group_by(Observation.source_id)
                .order_by(text("cnt DESC"))
                .limit(CACHE_WARM_TOP_N_SOURCES)
            )
            result = await session.execute(stmt)
            rows = result.all()

        for source_id, _ in rows:
            try:
                async with AsyncSessionLocal() as session:
                    from sqlalchemy import select as sa_select

                    observations_result = await session.execute(
                        sa_select(Observation)
                        .where(Observation.source_id == source_id)
                        .order_by(Observation.id.desc())
                        .limit(DEFAULT_PAGE_SIZE)
                    )
                    page = observations_result.scalars().all()
                    data = [
                        {
                            "id": r.id,
                            "source_id": r.source_id,
                            "timestamp": r.timestamp.isoformat(),
                        }
                        for r in page
                    ]
                    await set_observations_list(
                        source=source_id, skip=0, limit=DEFAULT_PAGE_SIZE, data=data
                    )
                    logger.info(
                        "cache_warm_source",
                        extra={"source_id": source_id, "rows": len(data)},
                    )
            except Exception as exc:
                logger.warning(
                    "cache_warm_source_error",
                    extra={"source_id": source_id, "error": str(exc)},
                )

    except Exception as exc:
        logger.warning("cache_warm_error", extra={"error": str(exc)})


async def cleanup_external_services() -> None:
    """Cleanup all external services during app shutdown.

    Cleanup order (LIFO from initialization):
    1. Kafka producer
    2. Cache cache
    3. Cache pub/sub

    Each cleanup is attempted even if a prior step fails.
    """

    # Cleanup Kafka (safe even if not connected)
    try:
        events = _events()
        if events is not None:
            await events.disconnect_producer()
            logger.info("events_producer_disconnected")
    except Exception as e:
        logger.warning(
            "events_producer_cleanup_error",
            extra={"error": str(e)},
        )

    # Cleanup Cache (safe even if not connected)
    try:
        cache = _cache()
        if cache is not None:
            await cache.disconnect_cache()
            logger.info("cache_disconnected")
    except Exception as e:
        logger.warning(
            "cache_cleanup_error",
            extra={"error": str(e)},
        )

    # Cleanup Cache Pub/Sub
    try:
        pubsub = _pubsub()
        if pubsub is not None:
            await pubsub.disconnect_pubsub()
            logger.info("pubsub_disconnected")
    except Exception as e:
        logger.warning(
            "pubsub_cleanup_error",
            extra={"error": str(e)},
        )
