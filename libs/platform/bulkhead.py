"""Async bulkhead primitive for dependency isolation.

A bulkhead limits concurrent calls per dependency and rejects overflow once a
small waiting queue is saturated. This prevents one slow dependency from
consuming all worker capacity.
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar


P = ParamSpec("P")
R = TypeVar("R")


class BulkheadRejectedError(Exception):
    """Raised when the bulkhead queue is full and the call is rejected."""


class AsyncBulkhead:
    """Concurrency/queue limiter for one downstream dependency."""

    def __init__(self, name: str, max_concurrency: int, max_queue: int = 0) -> None:
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be > 0")
        if max_queue < 0:
            raise ValueError("max_queue must be >= 0")

        self.name = name
        self.max_concurrency = max_concurrency
        self.max_queue = max_queue
        self._inflight = 0
        self._waiting = 0
        self._condition = asyncio.Condition()

    async def run(
        self, operation: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any
    ) -> Any:
        """Execute one operation through the bulkhead gate."""
        async with self._condition:
            if self._inflight >= self.max_concurrency:
                if self._waiting >= self.max_queue:
                    raise BulkheadRejectedError(f"Bulkhead '{self.name}' queue is full")

                self._waiting += 1
                try:
                    while self._inflight >= self.max_concurrency:
                        await self._condition.wait()
                finally:
                    self._waiting -= 1

            self._inflight += 1

        try:
            return await operation(*args, **kwargs)
        finally:
            async with self._condition:
                self._inflight -= 1
                self._condition.notify(1)


def bulkhead(
    name: str, max_concurrency: int, max_queue: int = 0
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorator factory for wrapping async dependency calls with a bulkhead."""

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        limiter = AsyncBulkhead(
            name=name,
            max_concurrency=max_concurrency,
            max_queue=max_queue,
        )

        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            return await limiter.run(func, *args, **kwargs)

        wrapper._bulkhead = limiter  # type: ignore[attr-defined]
        return wrapper

    return decorator
