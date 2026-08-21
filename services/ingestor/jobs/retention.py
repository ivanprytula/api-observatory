import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.cache import redis_lock
from services.ingestor.core.config import settings
from services.ingestor.metrics import (
    retention_observations_archived_total,
    retention_observations_deleted_total,
    retention_runs_total,
)
from services.ingestor.models import Observation, ObservationArchive


logger = logging.getLogger(__name__)


class RetentionVerificationError(RuntimeError):
    """Raised when selected observations cannot be verified in the archive."""


async def archive_old_observations(
    db: AsyncSession, *, apply: bool = False
) -> dict[str, Any]:
    """Archive one bounded batch of observations older than the retention window."""
    started_at = time.monotonic()
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(
        days=settings.retention_days
    )

    if apply and not settings.retention_enabled:
        retention_runs_total.labels(outcome="disabled").inc()
        return {
            "archived": 0,
            "deleted": 0,
            "eligible": 0,
            "duration_seconds": round(time.monotonic() - started_at, 6),
            "status": "disabled",
        }

    async with redis_lock("job:archive_old_observations", ttl_seconds=600) as acquired:
        if not acquired:
            retention_runs_total.labels(outcome="lock_held").inc()
            logger.info(
                "job_skipped_lock_held",
                extra={"job": "archive_old_observations"},
            )
            return {
                "archived": 0,
                "deleted": 0,
                "eligible": 0,
                "duration_seconds": 0.0,
                "skipped": True,
                "status": "lock_held",
            }

        async with db.begin():
            observations = list(
                (
                    await db.scalars(
                        select(Observation)
                        .where(Observation.timestamp < cutoff)
                        .order_by(Observation.timestamp, Observation.id)
                        .limit(settings.retention_batch_size)
                    )
                ).all()
            )

            if not observations:
                result = {
                    "archived": 0,
                    "deleted": 0,
                    "eligible": 0,
                    "duration_seconds": round(time.monotonic() - started_at, 6),
                    "status": "empty",
                }
            elif not apply:
                result = {
                    "archived": 0,
                    "deleted": 0,
                    "eligible": len(observations),
                    "duration_seconds": round(time.monotonic() - started_at, 6),
                    "status": "dry_run",
                }
            else:
                observation_ids = [observation.id for observation in observations]
                archived_ids = set(
                    (
                        await db.scalars(
                            select(ObservationArchive.id).where(
                                ObservationArchive.id.in_(observation_ids)
                            )
                        )
                    ).all()
                )
                new_archives = [
                    ObservationArchive(
                        id=observation.id,
                        source=observation.source,
                        timestamp=observation.timestamp,
                        raw_data=observation.raw_data,
                        tags=observation.tags,
                        processed=observation.processed,
                        processed_at=observation.processed_at,
                        tenant_id=observation.tenant_id,
                        created_at=observation.created_at,
                        updated_at=observation.updated_at,
                        deleted_at=observation.deleted_at,
                    )
                    for observation in observations
                    if observation.id not in archived_ids
                ]
                db.add_all(new_archives)
                await db.flush()

                verified_ids = set(
                    (
                        await db.scalars(
                            select(ObservationArchive.id).where(
                                ObservationArchive.id.in_(observation_ids)
                            )
                        )
                    ).all()
                )
                if verified_ids != set(observation_ids):
                    raise RetentionVerificationError(
                        "Archive verification failed; hot observations were not deleted"
                    )

                delete_result = cast(
                    CursorResult[Any],
                    await db.execute(
                        delete(Observation).where(
                            Observation.id.in_(observation_ids),
                            Observation.timestamp < cutoff,
                        ),
                    ),
                )
                deleted = delete_result.rowcount or 0
                if deleted != len(observation_ids):
                    raise RetentionVerificationError(
                        "Hot-table delete count differed from the verified archive batch"
                    )
                result = {
                    "archived": len(new_archives),
                    "deleted": deleted,
                    "eligible": len(observations),
                    "duration_seconds": round(time.monotonic() - started_at, 6),
                    "status": "applied",
                }

        retention_runs_total.labels(outcome=result["status"]).inc()
        if result["archived"]:
            retention_observations_archived_total.inc(result["archived"])
        if result["deleted"]:
            retention_observations_deleted_total.inc(result["deleted"])
        logger.info(
            "archive_old_observations_completed",
            extra={"cutoff": cutoff.isoformat(), **result},
        )
        return result
