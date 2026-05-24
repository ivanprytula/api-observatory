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

from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor import jobs as job_handlers
from services.ingestor.core.scheduler import JobScheduler


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

    # ========================================================================
    # Maintenance Jobs (Archive, Cleanup)
    # ========================================================================

    @scheduler.job(
        name="archive_old_records",
        trigger=None,  # Disabled by default; enable with CronTrigger(hour=3, minute=0)
        max_retries=2,
        timeout_seconds=600,
        tags={"archive", "maintenance"},
    )
    async def archive_job(db: AsyncSession) -> dict[str, Any]:
        """Archive old records to cold storage (Pillar 5 implementation).

        Enable by setting trigger=CronTrigger(hour=3, minute=0) or similar.
        """
        return await job_handlers.archive_old_records(db)

    logger.info(
        "jobs_registered",
        extra={
            "registered_job_count": len(scheduler._jobs),
            "jobs": list(scheduler._jobs.keys()),
        },
    )
