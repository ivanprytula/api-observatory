"""Ingestion job templates for scheduled and API-driven data ingestion.

Demonstrates both short-running API ingestion and long-running scheduled batch jobs.

Designed for:
- Multiple data sources (easily extensible)
- Data warehouse/datalake integration (idempotent, incremental)
- Future scaling to Celery/arq (job interface remains unchanged)

Job patterns:
1. API ingestion (short): sync on write, deduplication via unique constraint
2. Scheduled batch (long): periodic fetch from external source, retry on failure
3. Archive job (background): move data to cold storage (Pillar 2 archival strategy)
"""

from __future__ import annotations

import heapq
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.platform.retry import IdempotencyKeyTracker, exponential_backoff
from services.ingestor.api_schemas.records import RecordRequest
from services.ingestor.models import Record
from services.ingestor.repositories import records as crud


logger = logging.getLogger(__name__)


# Global deduplication tracker (in-memory for single-instance; Redis for distributed)
_dedup_tracker = IdempotencyKeyTracker(ttl_seconds=3600)


# ============================================================================
# API Ingestion Jobs (Short-Running)
# ============================================================================


async def ingest_api_single(
    db: AsyncSession,
    request: RecordRequest,
    idempotency_key: str | None = None,
) -> Record | None:
    """Ingest a single record from API (sync on write).

    This is the API ingestion pattern: immediate write + response.

    Args:
        db: Active async database session.
        request: RecordRequest payload from API.
        idempotency_key: Optional key for deduplication (prevents double-writes on retry).

    Returns:
        Inserted Record ORM instance, or None if duplicate (with idempotency_key).

    Notes:
        - Deduplication is in-memory (per-process). For distributed systems, use database
          unique constraints (already enforced on source + timestamp).
        - Uses connection from request lifespan, not a scheduled job.
    """
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

    record = await crud.create_record(db, request)

    logger.info(
        "ingest_api_single_created",
        extra={
            "record_id": record.id,
            "source": record.source,
            "idempotency_key": idempotency_key,
        },
    )

    return record


async def ingest_api_batch(
    db: AsyncSession,
    requests: list[RecordRequest],
    idempotency_key_prefix: str | None = None,
) -> dict[str, Any]:
    """Ingest a batch of records from API (bulk insert, optimized).

    API ingestion pattern for bulk uploads: batch insert + summary response.

    Args:
        db: Active async database session.
        requests: List of RecordRequest payloads.
        idempotency_key_prefix: Optional prefix for batch deduplication.

    Returns:
        Summary dict: {inserted: count, errors: count, first_error: str | None}.

    Notes:
        - Uses bulk insert with RETURNING for efficiency (1 round-trip).
        - Skips duplicates if idempotency_key_prefix is provided.
    """
    batch_key = (
        f"{idempotency_key_prefix}:{len(requests)}" if idempotency_key_prefix else None
    )

    if batch_key and _dedup_tracker.is_duplicate(batch_key):
        logger.info(
            "ingest_batch_duplicate_skipped",
            extra={"batch_key": batch_key, "count": len(requests)},
        )
        return {
            "inserted": 0,
            "errors": 0,
            "first_error": "Batch already processed (duplicate key)",
        }

    if batch_key:
        _dedup_tracker.mark_seen(batch_key)

    try:
        records = await crud.create_records_batch(db, requests)
        logger.info(
            "ingest_api_batch_created",
            extra={
                "inserted": len(records),
                "batch_key": batch_key,
                "sources": set(r.source for r in records),
            },
        )
        return {"inserted": len(records), "errors": 0, "first_error": None}

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


# ============================================================================
# Scheduled Batch Jobs (Long-Running) — Templates for Future Sources
# ============================================================================


@exponential_backoff(max_retries=3, base_delay=2.0, max_delay=60.0)
async def ingest_scheduled_batch_example(db: AsyncSession) -> dict[str, Any]:
    """Template for a scheduled batch ingestion job (runs every X hours).

    This is a placeholder job that demonstrates the pattern. For each new data source,
    create a similar job:
    1. Fetch from external source (API, S3, Kafka, etc)
    2. Transform to RecordRequest list
    3. Bulk insert with deduplication
    4. Return metrics

    Args:
        db: Active async database session (injected by scheduler).

    Returns:
        Summary dict: {source: str, inserted: count, duration_seconds: float}.

    Example usage in scheduler:

        @scheduler.job(
            name="ingest_source_a_hourly",
            trigger=IntervalTrigger(hours=1),
            max_retries=3,
            timeout_seconds=300,
            tags={"batch", "high_volume"},
        )
        async def ingest_source_a(db: AsyncSession) -> dict[str, Any]:
            return await ingest_scheduled_batch_template(
                db,
                source="source_a",
                fetch_fn=fetch_from_api_source_a,
                batch_size=1000,
            )
    """
    import time

    from services.ingestor.cache import redis_lock

    async with redis_lock("job:ingest_scheduled_batch_example") as acquired:
        if not acquired:
            logger.info(
                "job_skipped_lock_held",
                extra={"job": "ingest_scheduled_batch_example"},
            )
            return {"source": "example_source", "skipped": True, "reason": "lock_held"}

        start_time = time.perf_counter()

        # 1. Fetch external data (stub for example)
        source_name = "example_source"
        records_data = [
            {
                "source": source_name,
                "timestamp": datetime.now(UTC),
                "data": {"example": "data"},
                "tags": ["batch"],
            }
        ]

        # 2. Transform to RecordRequest
        requests = [RecordRequest(**r) for r in records_data]

        # 3. Bulk insert
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


@exponential_backoff(max_retries=2, base_delay=5.0)
async def archive_old_records(db: AsyncSession) -> dict[str, Any]:
    """Scheduled job to move old records to cold storage (Pillar 2 archival).

    Runs daily to move records >30 days old to records_archive partitions.

    Args:
        db: Active async database session (injected by scheduler).

    Returns:
        Summary dict: {archived: count, deleted: count, duration_seconds: float}.

    Notes:
        - Works in tandem with Pillar 2 data retention strategy.
        - For implementation: UPDATE records SET archive_date=NOW()
          WHERE created_at < NOW() - INTERVAL '30 days'
        - Placeholder for now (Pillar 5 implementation).
    """
    from services.ingestor.cache import redis_lock

    async with redis_lock("job:archive_old_records", ttl_seconds=600) as acquired:
        if not acquired:
            logger.info("job_skipped_lock_held", extra={"job": "archive_old_records"})
            return {
                "archived": 0,
                "deleted": 0,
                "duration_seconds": 0.0,
                "skipped": True,
            }

        # TODO: Implement archive logic using data-retention-archival.md strategy
        logger.info(
            "archive_old_records_placeholder",
            extra={"status": "pending_implementation"},
        )
        return {
            "archived": 0,
            "deleted": 0,
            "duration_seconds": 0.0,
            "status": "placeholder (Pillar 5)",
        }


# ============================================================================
# Health Check Helpers
# ============================================================================


async def get_ingestion_health(db: AsyncSession) -> dict[str, Any]:
    """Get ingestion pipeline health status.

    Used by `/health/ingestion` endpoint for monitoring and alerting.

    Returns:
        Dict with: records_count, last_record_time, api_insert_latency_ms, etc.
    """
    try:
        # Count recent records (last 24 hours)
        stmt = select(Record).where(
            Record.created_at >= datetime.now(UTC) - timedelta(days=1)
        )
        result = await db.execute(stmt)
        records_24h = len(result.scalars().all())

        # Get last record timestamp
        stmt = select(Record).order_by(Record.created_at.desc()).limit(1)
        result = await db.execute(stmt)
        last_record = result.scalar_one_or_none()
        last_record_time = last_record.created_at if last_record else None

        return {
            "status": "healthy",
            "records_24h": records_24h,
            "last_record_time": last_record_time.isoformat()
            if last_record_time
            else None,
            "ingestion_enabled": True,
        }

    except Exception:
        logger.exception("ingestion_health_check_failed")
        return {
            "status": "unhealthy",
            "error": "Internal ingestion health check failure",
            "ingestion_enabled": False,
        }


# =============================================================================
# DSA: Priority Queue  ·  Design Pattern: Command
# =============================================================================
#
# Pain diagnosed:
#   Job scheduling had no way to express "this job is more urgent than that one."
#   All jobs competed for the same FIFO queue; a high-priority real-time alert
#   could sit behind a long-running batch archive job.
#
# Solution — Command pattern:
#   Encapsulate every job as a self-contained Command object with an execute()
#   method, a priority, and an optional deadline.  The scheduler holds only the
#   abstract IngestionCommand interface — it never needs to import concrete jobs.
#   Commands are reusable (re-enqueue on failure), loggable, and undoable.
#
# Participants:
#   IngestionCommand         — abstract command (priority, deadline, execute, undo)
#   SingleRecordIngestCommand — concrete command: single-record ingest
#   BatchIngestCommand       — concrete command: bulk ingest
#   PriorityJobQueue         — invoker: heapq-backed, deadline-aware scheduler
#
# Data structure — min-heap via heapq:
#   push  O(log n)   heappush
#   pop   O(log n)   heappop (returns lowest priority value → highest urgency)
#   peek  O(1)       heap[0]
#   Total space O(n) where n = queued commands
#
# Priority convention: lower integer = higher urgency (1 = critical, 9 = batch).
# =============================================================================

# Priority constants (low number = more urgent)
PRIORITY_CRITICAL = 1  # Real-time alerts, user-triggered actions
PRIORITY_HIGH = 3  # Scheduled real-time feeds
PRIORITY_NORMAL = 5  # Standard scheduled batch jobs
PRIORITY_LOW = 7  # Archival, analytics
PRIORITY_BACKGROUND = 9  # Best-effort tasks (cleanup, stats)


class IngestionCommand(ABC):
    """Abstract Command for a unit of ingestion work.

    Each concrete command encapsulates everything needed to execute (and
    optionally undo) a job without the scheduler knowing any details.

    Priority convention: 1 = highest urgency, 9 = lowest.
    Deadline: ISO-formatted datetime string or None (no deadline).
    """

    @property
    @abstractmethod
    def priority(self) -> int:
        """Urgency level (1–9).  Lower = more urgent."""

    @property
    @abstractmethod
    def deadline(self) -> datetime | None:
        """Hard deadline for execution, or None if unbounded."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable command identifier for logging."""

    @abstractmethod
    async def execute(self, db: AsyncSession) -> dict[str, Any]:
        """Run the ingestion command.

        Args:
            db: Async database session provided by the scheduler.

        Returns:
            Result summary dict (inserted, errors, duration_seconds, …).
        """

    async def undo(self) -> None:  # noqa: B027 — intentional concrete no-op base
        """Optional rollback action (no-op by default).

        Override when the command can be undone (e.g., delete inserted records,
        publish a compensating Kafka event).
        """


@dataclass
class SingleRecordIngestCommand(IngestionCommand):
    """Concrete Command: ingest a single record at a given priority.

    Args:
        request:         Validated record payload.
        priority:        Urgency level (default: PRIORITY_NORMAL).
        deadline:        Hard cut-off time; None = no deadline.
        idempotency_key: Optional dedup key forwarded to ingest_api_single.
    """

    request: RecordRequest
    _priority: int = field(default=PRIORITY_NORMAL)
    _deadline: datetime | None = field(default=None)
    idempotency_key: str | None = field(default=None)

    @property
    def priority(self) -> int:
        return self._priority

    @property
    def deadline(self) -> datetime | None:
        return self._deadline

    @property
    def name(self) -> str:
        return f"single_ingest:{self.request.source}"

    async def execute(self, db: AsyncSession) -> dict[str, Any]:
        """Run single-record ingest and return summary."""
        record = await ingest_api_single(db, self.request, self.idempotency_key)
        return {
            "command": self.name,
            "record_id": record.id if record else None,
            "skipped": record is None,
        }


@dataclass
class BatchIngestCommand(IngestionCommand):
    """Concrete Command: bulk-ingest a list of records at a given priority.

    Args:
        requests:              List of validated record payloads.
        priority:              Urgency level (default: PRIORITY_NORMAL).
        deadline:              Hard cut-off time; None = no deadline.
        idempotency_key_prefix: Optional prefix for batch dedup.
    """

    requests: list[RecordRequest]
    _priority: int = field(default=PRIORITY_NORMAL)
    _deadline: datetime | None = field(default=None)
    idempotency_key_prefix: str | None = field(default=None)

    @property
    def priority(self) -> int:
        return self._priority

    @property
    def deadline(self) -> datetime | None:
        return self._deadline

    @property
    def name(self) -> str:
        sources = {r.source for r in self.requests}
        return f"batch_ingest:{','.join(sorted(sources))}[{len(self.requests)}]"

    async def execute(self, db: AsyncSession) -> dict[str, Any]:
        """Run batch ingest and return summary."""
        result = await ingest_api_batch(db, self.requests, self.idempotency_key_prefix)
        return {"command": self.name, **result}


class PriorityJobQueue:
    """Invoker: deadline-aware priority queue for IngestionCommand objects.

    Internally backed by Python's ``heapq`` module (min-heap on a list).  The
    heap entry is a tuple ``(effective_priority, tie_breaker, command)`` so that
    commands with the same priority are processed FIFO.

    Deadline promotion:
        If a command has a deadline within ``deadline_boost_secs`` seconds of
        the current time, its effective priority is temporarily promoted to
        ``PRIORITY_CRITICAL`` so it moves to the front of the queue.

    Usage::

        queue = PriorityJobQueue()
        queue.enqueue(BatchIngestCommand(requests, _priority=PRIORITY_LOW))
        queue.enqueue(SingleRecordIngestCommand(req, _priority=PRIORITY_HIGH))

        async with AsyncSessionLocal() as db:
            result = await queue.run_next(db)

    Args:
        deadline_boost_secs: Seconds before deadline at which to auto-promote.
    """

    def __init__(self, deadline_boost_secs: int = 30) -> None:
        self._heap: list[tuple[int, int, IngestionCommand]] = []
        self._counter: int = 0  # monotonic tie-breaker
        self._deadline_boost_secs = deadline_boost_secs

    # ------------------------------------------------------------------
    # Effective priority (considers deadline proximity)
    # ------------------------------------------------------------------

    def _effective_priority(self, cmd: IngestionCommand) -> int:
        """Return adjusted priority; boost to CRITICAL if deadline is imminent."""
        if cmd.deadline is not None:
            secs_remaining = (cmd.deadline - datetime.now(UTC)).total_seconds()
            if secs_remaining <= self._deadline_boost_secs:
                return PRIORITY_CRITICAL
        return cmd.priority

    # ------------------------------------------------------------------
    # Queue operations
    # ------------------------------------------------------------------

    def enqueue(self, cmd: IngestionCommand) -> None:
        """Add a command to the priority queue.

        Args:
            cmd: Any IngestionCommand concrete instance.
        """
        effective = self._effective_priority(cmd)
        heapq.heappush(self._heap, (effective, self._counter, cmd))
        self._counter += 1
        logger.info(
            "job_enqueued",
            extra={
                "command": cmd.name,
                "priority": cmd.priority,
                "effective_priority": effective,
                "queue_size": len(self._heap),
            },
        )

    def peek(self) -> IngestionCommand | None:
        """Return the highest-priority command without removing it."""
        if not self._heap:
            return None
        return self._heap[0][2]

    def dequeue(self) -> IngestionCommand | None:
        """Remove and return the highest-priority command, re-evaluating deadlines."""
        if not self._heap:
            return None
        # Re-evaluate deadlines for the entire heap (O(n) but n is bounded in practice)
        self._rebalance()
        _, _, cmd = heapq.heappop(self._heap)
        return cmd

    def _rebalance(self) -> None:
        """Re-compute effective priorities and re-heapify (O(n))."""
        updated = [
            (self._effective_priority(cmd), ctr, cmd) for _, ctr, cmd in self._heap
        ]
        heapq.heapify(updated)
        self._heap = updated

    async def run_next(self, db: AsyncSession) -> dict[str, Any] | None:
        """Dequeue and execute the highest-priority command.

        Args:
            db: Async database session for the command to use.

        Returns:
            Command result dict, or None if the queue is empty.
        """
        cmd = self.dequeue()
        if cmd is None:
            logger.info("job_queue_empty")
            return None

        logger.info(
            "job_executing",
            extra={"command": cmd.name, "priority": cmd.priority},
        )
        try:
            result = await cmd.execute(db)
            logger.info("job_completed", extra={"command": cmd.name, **result})
            return result
        except Exception as exc:
            logger.error(
                "job_failed",
                extra={"command": cmd.name, "error": str(exc)},
            )
            raise

    async def drain(self, db: AsyncSession) -> list[dict[str, Any]]:
        """Execute all queued commands in priority order.

        Args:
            db: Async database session shared across all commands.

        Returns:
            List of result dicts in execution order.
        """
        results: list[dict[str, Any]] = []
        while self._heap:
            result = await self.run_next(db)
            if result is not None:
                results.append(result)
        return results

    @property
    def size(self) -> int:
        """Number of commands currently in the queue."""
        return len(self._heap)

    def __repr__(self) -> str:
        return f"PriorityJobQueue(size={self.size})"


# Module-level default queue — replace in tests or reconfigure at startup.
_default_queue: PriorityJobQueue = PriorityJobQueue()


def get_job_queue() -> PriorityJobQueue:
    """Return the module-level job queue."""
    return _default_queue


def set_job_queue(queue: PriorityJobQueue) -> None:
    """Replace the active job queue (useful in tests)."""
    global _default_queue
    _default_queue = queue
