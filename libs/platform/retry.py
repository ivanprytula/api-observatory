"""Retry and backoff policies for resilient async operations.

Provides:
- Exponential backoff decorator with jitter
- Idempotency key tracking (for deduplication)
- Safe cancellation handling
- Structured failure reporting

Design principles:
- Backoff is applied between attempts, not concurrent
- Idempotency must be enforced by the caller (via unique constraints or explicit checks)
- Cancellation is always preserved (CancelledError re-raised)
- Failures are logged with context for debugging
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections import deque
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar


logger = logging.getLogger(__name__)
_SYSTEM_RANDOM = random.SystemRandom()

F = TypeVar("F", bound=Callable[..., Any])


class RetryBudgetExceededError(Exception):
    """Raised when retry attempts exceed the configured retry budget."""


class RetryBudget:
    """Sliding-window retry budget for one dependency.

    Use one shared budget per downstream dependency to avoid retry storms.
    """

    def __init__(self, max_retry_tokens: int, window_seconds: float) -> None:
        if max_retry_tokens <= 0:
            raise ValueError("max_retry_tokens must be > 0")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")

        self.max_retry_tokens = max_retry_tokens
        self.window_seconds = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _prune_expired(self, now: float) -> None:
        while self._timestamps and (now - self._timestamps[0]) > self.window_seconds:
            self._timestamps.popleft()

    async def consume_retry(self) -> bool:
        """Consume one retry token if available in the active window."""
        lock = self._get_lock()
        async with lock:
            now = time.monotonic()
            self._prune_expired(now)
            if len(self._timestamps) >= self.max_retry_tokens:
                return False
            self._timestamps.append(now)
            return True

    async def tokens_used(self) -> int:
        """Return active token count within the current window."""
        lock = self._get_lock()
        async with lock:
            now = time.monotonic()
            self._prune_expired(now)
            return len(self._timestamps)


def _apply_jitter(base_value: float, min_jitter: float, max_jitter: float) -> float:
    """Add random jitter to prevent thundering herd.

    Args:
        base_value: Base value to add jitter to.
        min_jitter: Minimum random offset (may be negative).
        max_jitter: Maximum random offset.

    Returns:
        base_value + uniform random value in [min_jitter, max_jitter].
    """
    return base_value + _SYSTEM_RANDOM.uniform(min_jitter, max_jitter)


def exponential_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    retry_budget: RetryBudget | None = None,
) -> Callable[[F], F]:
    """Decorator for exponential backoff with optional jitter on async functions.

    Usage:
        @exponential_backoff(max_retries=3, base_delay=1.0)
        async def call_external(payload: dict) -> dict:
            ...

    Args:
        max_retries: Number of retries (total attempts = max_retries + 1).
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay between attempts (caps exponential growth).
        jitter: If True, add ±20% variance to delay (prevents thundering herd).
        retry_budget: Optional shared retry budget for this dependency.

    Raises:
        Exception: The last exception after all retries exhausted.
        asyncio.CancelledError: Always re-raised (cancellation is never suppressed).
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    last_exception = e

                    if attempt < max_retries:
                        if retry_budget is not None:
                            budget_allowed = await retry_budget.consume_retry()
                            if not budget_allowed:
                                logger.error(
                                    "retry_budget_exhausted",
                                    extra={
                                        "function": func.__name__,
                                        "attempt": attempt + 1,
                                        "max_retries": max_retries + 1,
                                    },
                                )
                                raise RetryBudgetExceededError(
                                    f"Retry budget exhausted for {func.__name__}"
                                ) from e

                        delay = min(base_delay * (2**attempt), max_delay)
                        if jitter:
                            jitter_amount = delay * 0.2
                            delay = _apply_jitter(delay, -jitter_amount, jitter_amount)

                        logger.warning(
                            "retry_attempt",
                            extra={
                                "function": func.__name__,
                                "attempt": attempt + 1,
                                "max_retries": max_retries + 1,
                                "delay_seconds": delay,
                                "error": str(e),
                            },
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "retry_exhausted",
                            extra={
                                "function": func.__name__,
                                "total_attempts": max_retries + 1,
                                "error": str(last_exception),
                            },
                        )

            assert last_exception is not None
            raise last_exception

        return wrapper  # type: ignore

    return decorator


class IdempotencyKeyTracker:
    """Simple in-memory tracker for deduplication (single-instance deployments).

    For distributed systems, use a database or Redis-backed approach.

    Usage:
        tracker = IdempotencyKeyTracker()

        async def process_message(msg_id: str, data: dict) -> None:
            if tracker.is_duplicate(msg_id):
                logger.info("duplicate_skipped", extra={"key": msg_id})
                return
            tracker.mark_seen(msg_id)
    """

    def __init__(self, ttl_seconds: int = 3600) -> None:
        """Initialize tracker.

        Args:
            ttl_seconds: Time-to-live for tracked keys.
        """
        self._seen: dict[str, float] = {}
        self.ttl_seconds = ttl_seconds

    def is_duplicate(self, key: str) -> bool:
        """Check if key has been seen before and is not yet expired.

        Args:
            key: Idempotency key or message ID.

        Returns:
            True if key was previously marked as seen and not yet expired.
        """
        import time

        if key not in self._seen:
            return False
        age = time.time() - self._seen[key]
        if age > self.ttl_seconds:
            del self._seen[key]
            return False
        return True

    def mark_seen(self, key: str) -> None:
        """Mark a key as processed.

        Args:
            key: Idempotency key or message ID.
        """
        import time

        self._seen[key] = time.time()

    def cleanup_expired(self) -> None:
        """Remove expired entries (call periodically if tracker is long-lived)."""
        import time

        current_time = time.time()
        expired = [
            k for k, v in self._seen.items() if current_time - v > self.ttl_seconds
        ]
        for k in expired:
            del self._seen[k]
