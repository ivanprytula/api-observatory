"""Resource initialization and lifespan management for external services.

Encapsulates startup/shutdown logic for:
- Cache (optional)
- Kafka producer (optional)
- MongoDB (optional)

Design principle: Each service is independently initializable and gracefully
degrades if unavailable (fail-open for optional services).
"""

from __future__ import annotations

import logging
from importlib import import_module

from services.ingestor import cache, events, pubsub
from services.ingestor.config import settings


logger = logging.getLogger(__name__)


def _get_mongo_module():
    try:
        return import_module("services.ingestor.storage.mongo")
    except ImportError:
        return None


async def initialize_external_services() -> None:
    """Initialize all optional external services during app startup.

    Services are initialized in order of dependency:
    1. Cache (for caching)
    2. Broker (for events)
    3. MongoDB (for storage)

    Each service failure is logged but non-fatal (fail-open).
    """

    # Initialize cache backend (optional)
    if settings.cache_enabled:
        try:
            await cache.connect_cache(settings.cache_url)
            logger.info(
                "cache_connected",
                extra={"service": "cache", "url": settings.cache_url},
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
            await pubsub.connect_pubsub(settings.cache_url)
            logger.info(
                "pubsub_connected",
                extra={"service": "cache-pubsub", "url": settings.cache_url},
            )
        except Exception as e:
            logger.warning(
                "pubsub_connection_failed",
                extra={"service": "cache-pubsub", "error": str(e)},
            )

    # Initialize event broker producer (optional)
    if settings.broker_enabled:
        try:
            await events.connect_producer(settings.broker_url)
            logger.info(
                "events_producer_connected",
                extra={"service": "broker", "broker": settings.broker_url},
            )
        except Exception as e:
            logger.warning(
                "events_producer_connection_failed",
                extra={"service": "broker", "error": str(e)},
            )
            # Non-fatal: events are fail-open, app continues without broker

    # Initialize MongoDB (optional)
    mongo = _get_mongo_module()
    if settings.mongo_enabled and mongo is not None:
        try:
            await mongo.connect_mongo(settings.mongo_url, settings.mongo_db_name)
            logger.info(
                "mongo_connected",
                extra={"service": "mongodb", "db": settings.mongo_db_name},
            )
        except Exception as e:
            logger.warning(
                "mongo_connection_failed",
                extra={"service": "mongodb", "error": str(e)},
            )
            # Non-fatal: scraper routes degrade gracefully without MongoDB
    elif settings.mongo_enabled and mongo is None:
        logger.warning(
            "mongo_module_missing",
            extra={"service": "mongodb", "error": "storage.mongo unavailable"},
        )


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
        from services.ingestor.database import AsyncSessionLocal
        from services.ingestor.models import Observation

        async with AsyncSessionLocal() as session:
            stmt = (
                select(Observation.source, func.count(Observation.id).label("cnt"))
                .group_by(Observation.source)
                .order_by(text("cnt DESC"))
                .limit(CACHE_WARM_TOP_N_SOURCES)
            )
            result = await session.execute(stmt)
            rows = result.all()

        for source, _ in rows:
            try:
                async with AsyncSessionLocal() as session:
                    from sqlalchemy import select as sa_select

                    observations_result = await session.execute(
                        sa_select(Observation)
                        .where(Observation.source == source)
                        .order_by(Observation.id.desc())
                        .limit(DEFAULT_PAGE_SIZE)
                    )
                    page = observations_result.scalars().all()
                    data = [
                        {
                            "id": r.id,
                            "source": r.source,
                            "timestamp": r.timestamp.isoformat(),
                        }
                        for r in page
                    ]
                    await set_observations_list(
                        source=source, skip=0, limit=DEFAULT_PAGE_SIZE, data=data
                    )
                    logger.info(
                        "cache_warm_source", extra={"source": source, "rows": len(data)}
                    )
            except Exception as exc:
                logger.warning(
                    "cache_warm_source_error",
                    extra={"source": source, "error": str(exc)},
                )

    except Exception as exc:
        logger.warning("cache_warm_error", extra={"error": str(exc)})


async def cleanup_external_services() -> None:
    """Cleanup all external services during app shutdown.

    Cleanup order (LIFO from initialization):
    1. Kafka producer
    2. Cache cache
    3. MongoDB

    Each cleanup is attempted even if a prior step fails.
    """

    # Cleanup Kafka (safe even if not connected)
    try:
        await events.disconnect_producer()
        logger.info("events_producer_disconnected")
    except Exception as e:
        logger.warning(
            "events_producer_cleanup_error",
            extra={"error": str(e)},
        )

    # Cleanup Cache (safe even if not connected)
    try:
        await cache.disconnect_cache()
        logger.info("cache_disconnected")
    except Exception as e:
        logger.warning(
            "cache_cleanup_error",
            extra={"error": str(e)},
        )

    # Cleanup Cache Pub/Sub
    try:
        await pubsub.disconnect_pubsub()
        logger.info("pubsub_disconnected")
    except Exception as e:
        logger.warning(
            "pubsub_cleanup_error",
            extra={"error": str(e)},
        )

    # Cleanup MongoDB (safe even if not connected)
    mongo = _get_mongo_module()
    if mongo is not None:
        try:
            await mongo.disconnect_mongo()
            logger.info("mongo_disconnected")
        except Exception as e:
            logger.warning(
                "mongo_cleanup_error",
                extra={"error": str(e)},
            )
