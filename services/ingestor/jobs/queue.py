import heapq
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.observations import ObservationRequest


logger = logging.getLogger(__name__)

PRIORITY_CRITICAL = 1
PRIORITY_HIGH = 3
PRIORITY_NORMAL = 5
PRIORITY_LOW = 7
PRIORITY_BACKGROUND = 9


class IngestionCommand(ABC):
    @property
    @abstractmethod
    def priority(self) -> int: ...

    @property
    @abstractmethod
    def deadline(self) -> datetime | None: ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def execute(self, db: AsyncSession) -> dict[str, Any]: ...

    async def undo(self) -> None:  # noqa: B027 — intentional concrete no-op base
        ...


@dataclass
class SingleObservationIngestCommand(IngestionCommand):
    request: ObservationRequest
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
        from services.ingestor.jobs.ingestion import ingest_api_single

        observation = await ingest_api_single(db, self.request, self.idempotency_key)
        return {
            "command": self.name,
            "observation_id": observation.id if observation else None,
            "skipped": observation is None,
        }


@dataclass
class BatchIngestCommand(IngestionCommand):
    requests: list[ObservationRequest]
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
        from services.ingestor.jobs.ingestion import ingest_api_batch

        result = await ingest_api_batch(db, self.requests, self.idempotency_key_prefix)
        return {"command": self.name, **result}


class PriorityJobQueue:
    def __init__(self, deadline_boost_secs: int = 30) -> None:
        self._heap: list[tuple[int, int, IngestionCommand]] = []
        self._counter: int = 0
        self._deadline_boost_secs = deadline_boost_secs

    def _effective_priority(self, cmd: IngestionCommand) -> int:
        if cmd.deadline is not None:
            secs_remaining = (cmd.deadline - datetime.now(UTC)).total_seconds()
            if secs_remaining <= self._deadline_boost_secs:
                return PRIORITY_CRITICAL
        return cmd.priority

    def enqueue(self, cmd: IngestionCommand) -> None:
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
        if not self._heap:
            return None
        return self._heap[0][2]

    def dequeue(self) -> IngestionCommand | None:
        if not self._heap:
            return None
        self._rebalance()
        _, _, cmd = heapq.heappop(self._heap)
        return cmd

    def _rebalance(self) -> None:
        updated = [
            (self._effective_priority(cmd), ctr, cmd) for _, ctr, cmd in self._heap
        ]
        heapq.heapify(updated)
        self._heap = updated

    async def run_next(self, db: AsyncSession) -> dict[str, Any] | None:
        cmd = self.dequeue()
        if cmd is None:
            logger.info("job_queue_empty")
            return None

        logger.info(
            "job_executing",
            extra={
                "command": cmd.name,
                "priority": cmd.priority,
            },
        )
        try:
            result = await cmd.execute(db)
            logger.info("job_completed", extra={"command": cmd.name, **result})
            return result
        except Exception as exc:
            logger.error(
                "job_failed",
                extra={
                    "command": cmd.name,
                    "error": str(exc),
                },
            )
            raise

    async def drain(self, db: AsyncSession) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        while self._heap:
            result = await self.run_next(db)
            if result is not None:
                results.append(result)
        return results

    @property
    def size(self) -> int:
        return len(self._heap)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(size={self.size})"


_default_queue = PriorityJobQueue()


def get_job_queue() -> PriorityJobQueue:
    return _default_queue


def set_job_queue(queue: PriorityJobQueue) -> None:
    global _default_queue
    _default_queue = queue
