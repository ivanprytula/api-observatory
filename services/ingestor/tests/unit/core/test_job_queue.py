"""Unit tests for PriorityJobQueue and IngestionCommand scheduling logic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.jobs import (
    PRIORITY_BACKGROUND,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    IngestionCommand,
    PriorityJobQueue,
)


class _DummyCommand(IngestionCommand):
    """Concrete command for testing the priority queue."""

    def __init__(
        self,
        name: str,
        priority: int = PRIORITY_NORMAL,
        deadline: datetime | None = None,
        result: dict | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._name = name
        self._priority = priority
        self._deadline = deadline
        self._result = result or {"command": name}
        self._exc = exc

    @property
    def priority(self) -> int:
        return self._priority

    @property
    def deadline(self) -> datetime | None:
        return self._deadline

    @property
    def name(self) -> str:
        return self._name

    async def execute(self, db: AsyncSession) -> dict:
        if self._exc is not None:
            raise self._exc
        return self._result


@pytest.mark.unit
class TestPriorityQueueOrdering:
    def test_empty_queue_dequeue_returns_none(self) -> None:
        q = PriorityJobQueue()
        assert q.dequeue() is None

    def test_empty_queue_peek_returns_none(self) -> None:
        q = PriorityJobQueue()
        assert q.peek() is None

    def test_size_is_zero_for_new_queue(self) -> None:
        assert PriorityJobQueue().size == 0

    def test_enqueue_increases_size(self) -> None:
        q = PriorityJobQueue()
        q.enqueue(_DummyCommand("a"))
        assert q.size == 1

    def test_peek_returns_highest_priority_without_removing(self) -> None:
        q = PriorityJobQueue()
        low = _DummyCommand("low", PRIORITY_LOW)
        high = _DummyCommand("high", PRIORITY_HIGH)
        q.enqueue(low)
        q.enqueue(high)

        assert q.peek() is high
        assert q.size == 2  # unchanged

    def test_dequeue_returns_highest_priority_first(self) -> None:
        q = PriorityJobQueue()
        cmd_low = _DummyCommand("low", PRIORITY_LOW)
        cmd_high = _DummyCommand("high", PRIORITY_HIGH)
        cmd_bg = _DummyCommand("bg", PRIORITY_BACKGROUND)
        q.enqueue(cmd_low)
        q.enqueue(cmd_high)
        q.enqueue(cmd_bg)

        assert q.dequeue() is cmd_high
        assert q.dequeue() is cmd_low
        assert q.dequeue() is cmd_bg

    def test_fifo_order_for_same_priority(self) -> None:
        q = PriorityJobQueue()
        first = _DummyCommand("first", PRIORITY_NORMAL)
        second = _DummyCommand("second", PRIORITY_NORMAL)
        q.enqueue(first)
        q.enqueue(second)

        assert q.dequeue() is first
        assert q.dequeue() is second


@pytest.mark.unit
class TestDeadlineBoost:
    def test_deadline_pROMOTES_to_critical(self) -> None:
        q = PriorityJobQueue(deadline_boost_secs=30)
        now = datetime.now(UTC)
        imminent = _DummyCommand(
            "urgent", PRIORITY_NORMAL, deadline=now + timedelta(seconds=5)
        )
        normal = _DummyCommand("normal", PRIORITY_HIGH, deadline=None)
        q.enqueue(imminent)
        q.enqueue(normal)

        # Imminent deadline (NORMAL=5, but boosted to CRITICAL=1) beats HIGH=3
        first = q.dequeue()
        assert first is imminent

    def test_normal_priority_with_far_deadline_not_boosted(self) -> None:
        q = PriorityJobQueue(deadline_boost_secs=30)
        now = datetime.now(UTC)
        far = _DummyCommand("far", PRIORITY_NORMAL, deadline=now + timedelta(hours=1))
        high = _DummyCommand("high", PRIORITY_HIGH, deadline=None)
        q.enqueue(far)
        q.enqueue(high)

        # HIGH=3 beats NORMAL=5 (not boosted since deadline > 30s away)
        assert q.dequeue() is high


@pytest.mark.unit
class TestRunNext:
    async def test_run_next_executes_and_returns_result(self) -> None:
        q = PriorityJobQueue()
        cmd = _DummyCommand("task", result={"done": True})
        q.enqueue(cmd)

        result = await q.run_next(MagicMock(spec=AsyncSession))
        assert result == {"done": True}
        assert q.size == 0

    async def test_run_next_returns_none_when_empty(self) -> None:
        q = PriorityJobQueue()
        result = await q.run_next(MagicMock(spec=AsyncSession))
        assert result is None

    async def test_run_next_reraises_on_execution_error(self) -> None:
        q = PriorityJobQueue()
        cmd = _DummyCommand("broken", exc=RuntimeError("db down"))
        q.enqueue(cmd)

        with pytest.raises(RuntimeError, match="db down"):
            await q.run_next(MagicMock(spec=AsyncSession))
        # Queue should still be emptied (dequeued before execute)
        assert q.size == 0


@pytest.mark.unit
class TestDrain:
    async def test_drain_executes_all_in_priority_order(self) -> None:
        q = PriorityJobQueue()
        mock_db = MagicMock(spec=AsyncSession)
        low = _DummyCommand("low", PRIORITY_LOW)
        high = _DummyCommand("high", PRIORITY_HIGH)
        q.enqueue(low)
        q.enqueue(high)

        results = await q.drain(mock_db)
        assert len(results) == 2
        assert results[0]["command"] == "high"  # higher priority first
        assert results[1]["command"] == "low"

    async def test_drain_empty_queue_returns_empty_list(self) -> None:
        q = PriorityJobQueue()
        results = await q.drain(MagicMock(spec=AsyncSession))
        assert results == []

    async def test_drain_skips_none_results(self) -> None:
        q = PriorityJobQueue()
        # Use a command that returns a falsy result — should still be included
        cmd = _DummyCommand("task", result={})
        q.enqueue(cmd)

        results = await q.drain(MagicMock(spec=AsyncSession))
        # Empty dict is not None, so it IS included
        assert len(results) == 1
