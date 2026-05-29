"""Unit tests for bulkhead isolation and retry budget behavior."""

import asyncio

import pytest

from libs.platform.bulkhead import (
    AsyncBulkhead,
    BulkheadRejectedError,
    bulkhead,
)
from libs.platform.retry import (
    RetryBudget,
    RetryBudgetExceededError,
    exponential_backoff,
)


@pytest.mark.unit
async def test_retry_budget_caps_retries_across_calls() -> None:
    """Shared retry budget should reject retries after tokens are exhausted."""
    budget = RetryBudget(max_retry_tokens=1, window_seconds=60)
    call_count = 0

    @exponential_backoff(
        max_retries=3,
        base_delay=0,
        max_delay=0,
        jitter=False,
        retry_budget=budget,
    )
    async def always_fails() -> None:
        nonlocal call_count
        call_count += 1
        raise ValueError("downstream unavailable")

    with pytest.raises(RetryBudgetExceededError):
        await always_fails()

    assert call_count == 2  # 1 initial attempt + 1 retry token

    with pytest.raises(RetryBudgetExceededError):
        await always_fails()

    assert call_count == 3  # budget blocks retries, but initial call still executes


@pytest.mark.unit
async def test_retry_budget_window_expires_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retry budget should permit new retries after the budget window elapses."""
    budget = RetryBudget(max_retry_tokens=1, window_seconds=0.01)

    times = [100.0, 100.0, 100.02]

    def fake_monotonic() -> float:
        return times.pop(0) if times else 100.02

    monkeypatch.setattr("libs.platform.retry.time.monotonic", fake_monotonic)

    assert await budget.consume_retry() is True
    assert await budget.consume_retry() is False

    assert await budget.consume_retry() is True


@pytest.mark.unit
async def test_bulkhead_rejects_when_queue_is_full() -> None:
    """Bulkhead should reject overflow when concurrency and queue are saturated."""
    limiter = AsyncBulkhead(name="dependency-A", max_concurrency=1, max_queue=0)
    unblock = asyncio.Event()
    started = asyncio.Event()

    async def long_call() -> str:
        started.set()
        await unblock.wait()
        return "ok"

    task = asyncio.create_task(limiter.run(long_call))
    await started.wait()

    with pytest.raises(BulkheadRejectedError):
        await limiter.run(long_call)

    unblock.set()
    assert await task == "ok"


@pytest.mark.unit
async def test_bulkhead_decorator_uses_shared_limiter() -> None:
    """Decorator should apply one shared limiter instance per wrapped function."""
    unblock = asyncio.Event()
    started = asyncio.Event()

    @bulkhead(name="dependency-B", max_concurrency=1, max_queue=0)
    async def guarded_call() -> str:
        started.set()
        await unblock.wait()
        return "done"

    task = asyncio.create_task(guarded_call())
    await started.wait()

    with pytest.raises(BulkheadRejectedError):
        await guarded_call()

    unblock.set()
    assert await task == "done"
