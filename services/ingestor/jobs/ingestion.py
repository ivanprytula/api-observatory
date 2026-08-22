import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from libs.platform.retry import IdempotencyKeyTracker, exponential_backoff
from services.ingestor.api_schemas.observations import ObservationRequest
from services.ingestor.cache import redis_lock
from services.ingestor.models import Observation
from services.ingestor.repositories import observations as crud
from services.ingestor.repositories.source_registry import resolve_source_name


logger = logging.getLogger(__name__)

_dedup_tracker = IdempotencyKeyTracker(ttl_seconds=3600)


async def ingest_api_single(
    db: AsyncSession,
    request: ObservationRequest,
    idempotency_key: str | None = None,
) -> Observation | None:
    """Ingest a single observation from API (sync on write)."""
    if idempotency_key:
        if _dedup_tracker.is_duplicate(idempotency_key):
            logger.info(
                "ingest_duplicate_skipped",
                extra={
                    "idempotency_key": idempotency_key,
                    "source": request.source,
                },
            )
            return None
        _dedup_tracker.mark_seen(idempotency_key)

    observation = await crud.create_observation(db, request)

    logger.info(
        "ingest_api_single_created",
        extra={
            "observation_id": observation.id,
            "source": await resolve_source_name(db, observation.source_id),
            "idempotency_key": idempotency_key,
        },
    )

    return observation


async def ingest_api_batch(
    db: AsyncSession,
    requests: list[ObservationRequest],
    idempotency_key_prefix: str | None = None,
) -> dict[str, Any]:
    """Ingest a batch of observations from API (bulk insert, optimized)."""
    batch_key = (
        f"{idempotency_key_prefix}:{len(requests)}" if idempotency_key_prefix else None
    )

    if batch_key and _dedup_tracker.is_duplicate(batch_key):
        logger.info(
            "ingest_batch_duplicate_skipped",
            extra={
                "batch_key": batch_key,
                "count": len(requests),
            },
        )
        return {
            "inserted": 0,
            "errors": 0,
            "first_error": "Batch already processed (duplicate key)",
        }

    if batch_key:
        _dedup_tracker.mark_seen(batch_key)

    try:
        observations = await crud.create_observations_batch(db, requests)
        logger.info(
            "ingest_api_batch_created",
            extra={
                "inserted": len(observations),
                "batch_key": batch_key,
                "sources": set(r.source for r in requests),
            },
        )
        return {"inserted": len(observations), "errors": 0, "first_error": None}

    except Exception as e:
        logger.error(
            "ingest_api_batch_failed",
            extra={
                "batch_key": batch_key,
                "count": len(requests),
                "error": str(e),
            },
        )
        return {"inserted": 0, "errors": len(requests), "first_error": str(e)}


@exponential_backoff(max_retries=3, base_delay=2.0, max_delay=60.0)
async def ingest_scheduled_batch_example(db: AsyncSession) -> dict[str, Any]:
    """Template for a scheduled batch ingestion job (runs every X hours)."""
    import time

    async with redis_lock("job:ingest_scheduled_batch_example") as acquired:
        if not acquired:
            logger.info(
                "job_skipped_lock_held",
                extra={"job": "ingest_scheduled_batch_example"},
            )
            return {"source": "example_source", "skipped": True, "reason": "lock_held"}

        start_time = time.perf_counter()

        source_name = "example_source"
        observations_data: list[dict[str, Any]] = [
            {
                "source": source_name,
                "timestamp": datetime.now(UTC),
                "data": {"example": "data"},
                "tags": ["batch"],
            }
        ]

        requests = [ObservationRequest(**r) for r in observations_data]

        batch_result = await ingest_api_batch(
            db,
            requests,
            idempotency_key_prefix=f"{source_name}_{datetime.now(UTC).date()}",
        )

        duration = time.perf_counter() - start_time

        result = {
            "source": source_name,
            "inserted": batch_result["inserted"],
            "errors": batch_result["errors"],
            "duration_seconds": duration,
        }

        logger.info(
            "ingest_scheduled_batch_completed",
            extra=result,
        )

        return result
