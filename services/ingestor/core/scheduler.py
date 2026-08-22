"""Lightweight job scheduling abstraction built on APScheduler.

Designed for:
- Single-instance deployments (dev/test) via APScheduler
- Easy migration to Celery/arq when horizontal scaling needed
- Mixed workloads: short-running API ingestion + long-running scheduled jobs
- Proper lifecycle: startup/shutdown, cancellation handling, health monitoring

Architecture:
- JobScheduler: wraps APScheduler, manages job lifecycle
- Job: dataclass defining name, schedule, handler, retry policy
- HealthCheck: tracks job execution health (last_run, success rate, errors)
- Jobs registered in lifespan startup/shutdown

For distributed scaling (Phase 2+):
- Replace APScheduler with Celery/arq (same Job interface, different backend)
- Move job state to Cache/broker instead of in-memory
- Add worker pool configuration, result backend, task tracing

Example usage:

    scheduler = JobScheduler()

    @scheduler.job(
        name="batch_ingest_daily",
        trigger="cron",
        hour=0,
        minute=0,
        max_retries=3,
    )
    async def ingest_daily_batch(db: AsyncSession) -> dict[str, Any]:
        '''Scheduled job handler — called by scheduler at 00:00 UTC daily.'''
            observations = await fetch_external_source()
                inserted = await crud.create_observations_batch(db, observations)
        return {"inserted": len(inserted), "source": "daily_batch"}

    # In app lifespan:
    async with scheduler.start(db_session_factory):  # Context manager ensures cleanup
        yield
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from libs.platform.job_types import Job, JobHealthMetrics
from services.ingestor.core.handlers import wrap_job_handler


logger = logging.getLogger(__name__)


class JobScheduler:
    """Lightweight job scheduler wrapping APScheduler.

    Responsibilities:
    - Register jobs with APScheduler
    - Manage job lifecycle (startup/shutdown)
    - Track job health and metrics
    - Handle retries and timeouts
    - Provide health check endpoints

    Example:
        scheduler = JobScheduler()

        @scheduler.job(
            name="ingest_hourly",
            trigger=IntervalTrigger(hours=1),
            max_retries=3,
            tags={"critical", "high_volume"},
        )
        async def hourly_ingest(db: AsyncSession) -> dict[str, Any]:
            ...

        async with scheduler.start(session_factory):
            yield  # Jobs run in background while app is running
    """

    def __init__(self) -> None:
        """Initialize scheduler (not started until .start() is called)."""
        self._scheduler = AsyncIOScheduler()
        self._jobs: dict[str, Job] = {}
        self._session_factory: Callable[[], Any] | None = None

    @property
    def running(self) -> bool:
        return self._scheduler.running

    def job(
        self,
        name: str,
        trigger: CronTrigger | IntervalTrigger | None,
        max_retries: int = 3,
        timeout_seconds: int | None = None,
        tags: set[str] | None = None,
    ) -> Callable[[Callable], Callable]:
        """Decorator to register a scheduled job.

        Args:
            name: Unique job name.
            trigger: APScheduler trigger (CronTrigger, IntervalTrigger, etc).
            max_retries: Max retries on failure.
            timeout_seconds: Job timeout in seconds (None = no timeout).
            tags: Metadata tags for monitoring.

        Returns:
            Decorator that registers the handler and returns it unchanged.

        Example:
            @scheduler.job(
                name="daily_ingest",
                trigger=CronTrigger(hour=0, minute=0),
                max_retries=3,
            )
            async def daily_ingest(db: AsyncSession) -> dict[str, Any]:
                ...
        """

        def decorator(handler: Callable) -> Callable:
            job_obj = Job(
                name=name,
                handler=handler,
                trigger=trigger,
                max_retries=max_retries,
                timeout_seconds=timeout_seconds,
                tags=tags or set(),
            )
            self._jobs[name] = job_obj
            # If the scheduler is already running (e.g. a job registered
            # dynamically after startup, not just during initial boot),
            # wire it into the live APScheduler engine immediately —
            # otherwise it would only ever be bookkeeping in self._jobs
            # until the next process restart.
            if self._scheduler.running:
                self._activate_job(name, job_obj)
            return handler

        return decorator

    def _activate_job(self, job_name: str, job_obj: Job) -> None:
        """Wire a single job into the live APScheduler engine."""
        if job_obj.trigger is None:
            logger.info(
                "job_registration_skipped",
                extra={"job_name": job_name, "reason": "trigger_disabled"},
            )
            return

        # Wrap handler to inject session and track metrics. session_factory is
        # only unset before the initial start() call, and _activate_job is only
        # ever reached after that (either from within start()'s own loop, or
        # from the job() decorator once self._scheduler.running is True).
        assert self._session_factory is not None, (
            "_activate_job called before scheduler.start()"
        )
        wrapped_handler = wrap_job_handler(job_obj, self._session_factory)

        self._scheduler.add_job(
            wrapped_handler,
            trigger=job_obj.trigger,
            id=job_name,
            name=job_name,
            replace_existing=True,
        )

        logger.info(
            "job_registered",
            extra={
                "job_name": job_name,
                "trigger": str(job_obj.trigger),
                "tags": list(job_obj.tags),
            },
        )

    async def start(self, session_factory: Callable[[], Any]) -> AsyncIOScheduler:
        """Start the scheduler and register all jobs.

        Args:
            session_factory: Callable that returns a new AsyncSession (for job dependency injection)

        Returns:
            The AsyncIOScheduler instance (can be used with `async with scheduler.start(..): yield`)

        Usage:
            async with scheduler.start(get_db_session):
                yield  # Jobs run in background
        """
        self._session_factory = session_factory

        for job_name, job_obj in self._jobs.items():
            self._activate_job(job_name, job_obj)

        self._scheduler.start()
        logger.info("scheduler_started", extra={"job_count": len(self._jobs)})

        return self._scheduler

    async def stop(self) -> None:
        """Stop the scheduler and shut down all jobs."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            await asyncio.sleep(0)
            logger.info("scheduler_stopped")

    def get_job_health(self, job_name: str) -> JobHealthMetrics | None:
        """Get health metrics for a specific job.

        Args:
            job_name: Name of the job.

        Returns:
            JobHealthMetrics instance, or None if job not found.
        """
        job = self._jobs.get(job_name)
        return job.health if job else None

    def get_all_jobs_health(self) -> dict[str, JobHealthMetrics]:
        """Get health metrics for all jobs.

        Returns:
            Dict mapping job name to JobHealthMetrics.
        """
        return {name: job.health for name, job in self._jobs.items()}

    def get_next_run_times(self) -> dict[str, datetime | None]:
        """Get next scheduled run time for each job.

        Returns:
            Dict mapping job name to next run datetime (or None if not scheduled).
        """
        result = {}
        for job_name in self._jobs:
            apscheduler_job = self._scheduler.get_job(job_name)
            result[job_name] = (
                apscheduler_job.next_run_time if apscheduler_job else None
            )
        return result

    def has_job(self, job_name: str) -> bool:
        """Check if a job is registered in the scheduler.

        Args:
            job_name: Name of the job.

        Returns:
            True if the job is registered.
        """
        return job_name in self._jobs

    def pause_job(self, job_name: str) -> None:
        """Pause a running APScheduler job.

        If the job is not found in APScheduler (e.g. not yet activated),
        this is a no-op.

        Args:
            job_name: Name of the job to pause.
        """
        apscheduler_job = self._scheduler.get_job(job_name)
        if apscheduler_job is not None:
            self._scheduler.pause_job(job_name)
            logger.info("job_paused", extra={"job_name": job_name})

    def resume_job(self, job_name: str) -> None:
        """Resume a paused APScheduler job.

        If the job is not found in self._jobs, logs a warning and returns.
        If the job is registered but not yet activated in APScheduler,
        activates it first.

        Args:
            job_name: Name of the job to resume.
        """
        job_obj = self._jobs.get(job_name)
        if job_obj is None:
            logger.warning("resume_job_not_found", extra={"job_name": job_name})
            return

        apscheduler_job = self._scheduler.get_job(job_name)
        if apscheduler_job is not None:
            self._scheduler.resume_job(job_name)
            logger.info("job_resumed", extra={"job_name": job_name})
        else:
            self._activate_job(job_name, job_obj)
            logger.info("job_activated_on_resume", extra={"job_name": job_name})
