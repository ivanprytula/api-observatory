"""In-process background worker pool for large batch ingestion (Pillar 5 prototype)."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from services.ingestor import jobs
from services.ingestor.api_schemas.observations import ObservationRequest
from services.ingestor.database import AsyncSessionLocal
from services.ingestor.metrics import (
    background_jobs_active,
    background_jobs_in_queue,
    background_jobs_processed_total,
    background_jobs_submitted_total,
)


logger = logging.getLogger(__name__)

TaskState = Literal["queued", "running", "succeeded", "failed", "cancelled"]


@dataclass
class BackgroundTaskStatus:
    """State snapshot for a submitted background batch ingestion task."""

    task_id: str
    status: TaskState
    batch_size: int
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class BackgroundWorkerPool:
    """Lightweight async worker queue.

    This is intentionally in-process and non-distributed. It provides a practical
    bridge between scheduler-only execution and full broker-backed workers.
    """

    def __init__(
        self,
        worker_count: int,
        queue_size: int,
        max_tracked_tasks: int,
        processor: Callable[[list[ObservationRequest]], Awaitable[dict[str, Any]]]
        | None = None,
        on_task_failed: Callable[[BackgroundTaskStatus], Awaitable[None]] | None = None,
    ) -> None:
        self._worker_count = worker_count
        self._queue: asyncio.Queue[tuple[str, list[ObservationRequest]]] = (
            asyncio.Queue(maxsize=queue_size)
        )
        self._workers: list[asyncio.Task[None]] = []
        self._statuses: dict[str, BackgroundTaskStatus] = {}
        self._order: deque[str] = deque()
        self._max_tracked_tasks = max_tracked_tasks
        self._running = False
        self._processor = processor or self._default_processor
        self._on_task_failed = on_task_failed

    @property
    def running(self) -> bool:
        """Return whether worker pool has active consumer tasks."""
        return self._running

    async def start(self) -> None:
        """Start the worker consumer tasks."""
        if self._running:
            return

        self._running = True
        self._workers = [
            asyncio.create_task(self._worker_loop(i), name=f"bg-worker-{i}")
            for i in range(self._worker_count)
        ]
        background_jobs_in_queue.set(0)
        logger.info(
            "background_worker_pool_started",
            extra={
                "worker_count": self._worker_count,
                "queue_capacity": self._queue.maxsize,
            },
        )

    async def stop(self) -> None:
        """Stop workers and wait for graceful cancellation."""
        if not self._running:
            return

        self._running = False
        for task in self._workers:
            task.cancel()

        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        background_jobs_active.set(0)
        logger.info("background_worker_pool_stopped")

    async def submit_batch_ingest(
        self, observations: list[ObservationRequest]
    ) -> BackgroundTaskStatus:
        """Queue a large batch ingestion task for asynchronous processing."""
        if not self._running:
            raise RuntimeError("Background worker pool is not running")
        if self._queue.full():
            raise RuntimeError("Background queue is full")

        task_id = str(uuid4())
        status = BackgroundTaskStatus(
            task_id=task_id,
            status="queued",
            batch_size=len(observations),
            queued_at=datetime.now(UTC),
        )
        self._statuses[task_id] = status
        self._order.append(task_id)
        self._trim_status_history()

        self._queue.put_nowait((task_id, observations))
        background_jobs_submitted_total.labels(kind="batch_ingest").inc()
        background_jobs_in_queue.set(self._queue.qsize())

        return status

    def get_task_status(self, task_id: str) -> BackgroundTaskStatus | None:
        """Return status for a known task id."""
        return self._statuses.get(task_id)

    def health_summary(self) -> dict[str, Any]:
        """Return worker-pool health and task counters."""
        counters: dict[str, int] = {
            "queued": 0,
            "running": 0,
            "succeeded": 0,
            "failed": 0,
            "cancelled": 0,
        }
        for status in self._statuses.values():
            counters[status.status] += 1

        return {
            "running": self._running,
            "worker_count": self._worker_count,
            "queue_size": self._queue.qsize(),
            "queue_capacity": self._queue.maxsize,
            "tracked_tasks": len(self._statuses),
            "tasks": counters,
        }

    async def _worker_loop(self, worker_index: int) -> None:
        """Continuously consume queued tasks until cancellation."""
        while True:
            try:
                task_id, observations = await self._queue.get()
            except asyncio.CancelledError:
                raise

            status = self._statuses[task_id]
            status.status = "running"
            status.started_at = datetime.now(UTC)
            background_jobs_active.inc()
            background_jobs_in_queue.set(self._queue.qsize())

            try:
                result = await self._processor(observations)
                status.status = "succeeded"
                status.result = result
                background_jobs_processed_total.labels(
                    kind="batch_ingest", status="succeeded"
                ).inc()
                logger.info(
                    "background_task_succeeded",
                    extra={
                        "task_id": task_id,
                        "worker_index": worker_index,
                        "batch_size": status.batch_size,
                    },
                )
            except asyncio.CancelledError:
                status.status = "cancelled"
                status.error = "worker task cancelled"
                background_jobs_processed_total.labels(
                    kind="batch_ingest", status="cancelled"
                ).inc()
                raise
            except Exception as exc:
                status.status = "failed"
                status.error = str(exc)
                background_jobs_processed_total.labels(
                    kind="batch_ingest", status="failed"
                ).inc()
                if self._on_task_failed is not None:
                    try:
                        await self._on_task_failed(status)
                    except Exception as callback_exc:
                        logger.warning(
                            "background_task_failed_callback_error",
                            extra={
                                "task_id": task_id,
                                "error": str(callback_exc),
                            },
                        )
                logger.error(
                    "background_task_failed",
                    extra={
                        "task_id": task_id,
                        "worker_index": worker_index,
                        "error": str(exc),
                    },
                )
            finally:
                status.finished_at = datetime.now(UTC)
                self._queue.task_done()
                background_jobs_active.dec()
                background_jobs_in_queue.set(self._queue.qsize())

    async def _default_processor(
        self, observations: list[ObservationRequest]
    ) -> dict[str, Any]:
        """Default processing strategy: ingest via existing batch ingestion logic."""
        async with AsyncSessionLocal() as session:
            return await jobs.ingest_api_batch(
                session,
                observations,
                idempotency_key_prefix=f"bg-batch-{datetime.now(UTC).date()}",
            )

    def _trim_status_history(self) -> None:
        """Bound in-memory status history to avoid unbounded growth."""
        while len(self._order) > self._max_tracked_tasks:
            oldest_id = self._order.popleft()
            self._statuses.pop(oldest_id, None)
