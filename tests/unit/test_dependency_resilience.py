"""Focused behavior tests for composed downstream resilience controls."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from libs.platform.bulkhead import BulkheadRejectedError
from libs.platform.resilience import DependencyResilience
from libs.platform.retry import RetryBudget


pytestmark = pytest.mark.unit


async def test_retries_transient_transport_error_once() -> None:
    resilience = DependencyResilience(
        "test-retry",
        max_concurrency=1,
        max_queue=0,
        retry_budget=RetryBudget(max_retry_tokens=2, window_seconds=60),
    )
    operation = AsyncMock(side_effect=[httpx.ConnectError("offline"), "ok"])

    with patch("libs.platform.retry.asyncio.sleep", new=AsyncMock()):
        result = await resilience.call(operation)

    assert result == "ok"
    assert operation.await_count == 2


async def test_does_not_retry_validation_or_cancellation_errors() -> None:
    resilience = DependencyResilience("test-no-retry", max_concurrency=1, max_queue=0)
    invalid = AsyncMock(side_effect=ValueError("bad payload"))
    cancelled = AsyncMock(side_effect=asyncio.CancelledError())

    with pytest.raises(ValueError, match="bad payload"):
        await resilience.call(invalid)
    with pytest.raises(asyncio.CancelledError):
        await resilience.call(cancelled)

    assert invalid.await_count == 1
    assert cancelled.await_count == 1


async def test_bulkhead_rejects_overflow() -> None:
    resilience = DependencyResilience("test-bulkhead", max_concurrency=1, max_queue=0)
    started = asyncio.Event()
    unblock = asyncio.Event()

    async def slow_operation() -> str:
        started.set()
        await unblock.wait()
        return "done"

    first = asyncio.create_task(resilience.call(slow_operation))
    await started.wait()
    with pytest.raises(BulkheadRejectedError):
        await resilience.call(slow_operation)

    unblock.set()
    assert await first == "done"
