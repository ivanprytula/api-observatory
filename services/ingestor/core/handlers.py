"""Job handler wrapping utilities for scheduling, retries, timeouts, and metrics.

Separates concerns of job execution from job scheduling:
- Session dependency injection
- Timeout enforcement
- Health metrics tracking
- Structured error logging

Design principle: A handler wrapper is a composable layer that transforms
a raw job function into one compatible with APScheduler.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from libs.platform.job_types import Job
from services.ingestor.metrics import job_duration_seconds, job_executions_total


logger = logging.getLogger(__name__)


def wrap_job_handler(
    job_obj: Job,
    session_factory: Callable[[], Any],
) -> Callable[[], Any]:
    """Wrap a job handler to inject session, handle timeouts, and track metrics.

    Args:
        job_obj: Job definition (includes handler, timeout, max_retries, health).
        session_factory: Callable that creates a new AsyncSession.

    Returns:
        Wrapped handler ready for APScheduler (no arguments, returns dict[str, Any]).

    Responsibilities:
        1. Create session from factory
        2. Execute handler with timeout
        3. Update health metrics on success/failure
        4. Log execution details
    """

    async def wrapped() -> dict[str, Any]:
        """Execute job with timeout and health tracking."""
        if session_factory is None:
            raise RuntimeError("Handler wrapper called without session_factory")

        session = session_factory()

        try:
            start_time = asyncio.get_event_loop().time()

            # Execute handler with optional timeout
            if job_obj.timeout_seconds:
                result = await asyncio.wait_for(
                    job_obj.handler(session),
                    timeout=job_obj.timeout_seconds,
                )
            else:
                result = await job_obj.handler(session)

            duration = asyncio.get_event_loop().time() - start_time

            # Observation success in health metrics
            job_obj._health.last_run_at = datetime.now(UTC)
            job_obj._health.last_run_duration_seconds = duration
            job_obj._health.success_count += 1
            job_obj._health.last_error = None

            job_executions_total.labels(job_name=job_obj.name, status="success").inc()
            job_duration_seconds.labels(job_name=job_obj.name).observe(duration)

            logger.info(
                "job_executed_successfully",
                extra={
                    "job_name": job_obj.name,
                    "duration_seconds": duration,
                    "result": result,
                },
            )

            return result

        except TimeoutError as e:
            # Observation timeout in health metrics
            job_obj._health.last_run_at = datetime.now(UTC)
            job_obj._health.failure_count += 1
            job_obj._health.last_error = str(e) or "timeout exceeded"

            job_executions_total.labels(job_name=job_obj.name, status="timeout").inc()

            logger.error(
                "job_execution_timeout",
                extra={
                    "job_name": job_obj.name,
                    "timeout_seconds": job_obj.timeout_seconds,
                    "error": str(e) or "timeout exceeded",
                },
            )
            raise

        except asyncio.CancelledError:
            # Always preserve cancellation without observationing as failure
            logger.info(
                "job_execution_cancelled",
                extra={"job_name": job_obj.name},
            )
            raise

        except Exception as e:
            # Observation failure in health metrics
            job_obj._health.last_run_at = datetime.now(UTC)
            job_obj._health.failure_count += 1
            job_obj._health.last_error = str(e)

            job_executions_total.labels(job_name=job_obj.name, status="failed").inc()

            logger.error(
                "job_execution_failed",
                extra={
                    "job_name": job_obj.name,
                    "error": str(e),
                },
            )
            raise
        finally:
            close_method = getattr(session, "close", None)
            if callable(close_method):
                maybe_awaitable = close_method()
                if asyncio.iscoroutine(maybe_awaitable):
                    await maybe_awaitable

    return wrapped
