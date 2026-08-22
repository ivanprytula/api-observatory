"""Job registry and initialization for scheduled ingestion jobs.

Centralizes job registration logic, separating concerns:
- Job definitions (name, trigger, handler)
- Job registration (decorator pattern)
- Scheduled vs template jobs
- Future extensibility (add new sources easily)

Design principle: Jobs are registered once at app startup via the registry,
not scattered throughout main.py.
"""

from __future__ import annotations

import logging
from typing import Any

from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor import jobs as job_handlers
from services.ingestor.core.scheduler import JobScheduler
from services.ingestor.models import SourceProfile


logger = logging.getLogger(__name__)


def register_jobs(scheduler: JobScheduler) -> None:
    """Register all scheduled ingestion jobs.

    This is the single point of entry for job registration. Add new jobs here
    as new data sources are integrated.

    Args:
        scheduler: JobScheduler instance to register jobs with.
    """

    # ========================================================================
    # Scheduled Batch Ingestion Jobs
    # ========================================================================

    @scheduler.job(
        name="ingest_scheduled_batch_example",
        trigger=None,  # Disabled by default; enable with IntervalTrigger(hours=1)
        max_retries=3,
        timeout_seconds=300,
        tags={"batch", "example"},
    )
    async def scheduled_batch_job(db: AsyncSession) -> dict[str, Any]:
        """Template for scheduled batch ingestion jobs (disabled by default).

        Enable by setting trigger=IntervalTrigger(hours=1) or similar.
        """
        return await job_handlers.ingest_scheduled_batch_example(db)

    logger.info(
        "jobs_registered",
        extra={
            "registered_job_count": len(scheduler._jobs),
            "jobs": list(scheduler._jobs.keys()),
        },
    )


async def register_source_probe_jobs(scheduler: JobScheduler, db: AsyncSession) -> int:
    """Register one probe job per active source profile.

    Returns the number of newly registered probe jobs.
    """
    stmt = select(SourceProfile).where(
        SourceProfile.deleted_at.is_(None),
        SourceProfile.is_active.is_(True),
    )
    sources = list((await db.execute(stmt)).scalars().all())

    registered = 0
    for source in sources:
        source_id = source.id
        interval_seconds = max(1, int(source.probe_interval_seconds))
        job_name = f"probe_source_{source_id}"
        if job_name in scheduler._jobs:
            continue

        @scheduler.job(
            name=job_name,
            trigger=IntervalTrigger(seconds=interval_seconds),
            max_retries=0,
            timeout_seconds=15,
            tags={"probe", "source-health"},
        )
        async def source_probe_job(
            session: AsyncSession, _source_id: int = source_id
        ) -> dict[str, Any]:
            return await job_handlers.run_source_probe(session, _source_id)

        snapshot_job_name = f"contract_snapshot_source_{source_id}"
        if snapshot_job_name not in scheduler._jobs:
            snapshot_interval = max(300, interval_seconds * 5)

            @scheduler.job(
                name=snapshot_job_name,
                trigger=IntervalTrigger(seconds=snapshot_interval),
                max_retries=1,
                timeout_seconds=30,
                tags={"contract-drift", "snapshot"},
            )
            async def source_snapshot_job(
                session: AsyncSession, _source_id: int = source_id
            ) -> dict[str, Any]:
                return await job_handlers.run_source_contract_snapshot(
                    session, _source_id
                )

        registered += 1

    logger.info(
        "source_probe_jobs_registered",
        extra={
            "registered_probe_jobs": registered,
            "total_scheduler_jobs": len(scheduler._jobs),
        },
    )
    return registered
