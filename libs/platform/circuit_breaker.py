"""Centralized async circuit breaker — libs.platform.

Two usage styles:

1. Class-based (context manager + call()):

    breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)
    result = await breaker.call(some_async_fn, *args)

    async with breaker:
        await do_something()

2. Decorator factory:

    @circuit_breaker(failure_threshold=5, recovery_timeout=30)
    async def call_external_service(payload: dict) -> None:
        ...  # any exception here is counted as a failure

States (classic three-state machine):

    CLOSED ──(failures >= threshold)──► OPEN
      ▲                                   │
      │                                   │ (recovery_timeout elapsed)
      │                                 HALF_OPEN
      │                                   │
      └────────(next call succeeds)───────┘

- CLOSED:    Normal operation. Failures are counted.
- OPEN:      Calls rejected immediately (CircuitOpenError).
- HALF_OPEN: One probe call is allowed. Success → CLOSED. Failure → OPEN.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any


logger = logging.getLogger(__name__)


def _attach_circuit_breaker(function: Any, breaker: Any) -> None:
    """Expose decorator state for diagnostics without widening call signatures."""
    function._circuit_breaker = breaker


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when a guarded call is attempted while the circuit is OPEN."""


# ---------------------------------------------------------------------------
# Class-based style — context manager + call()
# ---------------------------------------------------------------------------


class CircuitBreaker:
    """Stateful async circuit breaker.

    Usage::

        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)

        # run a protected call
        result = await breaker.call(some_async_fn, *args)

        # or use as async context manager
        async with breaker:
            await do_something()

    The context manager observations success/failure automatically based on whether
    an exception escaped the block.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_successes: int = 1,
        time_func: Callable[[], float] = time.monotonic,
        is_failure: Callable[[BaseException], bool] | None = None,
    ) -> None:
        self._failure_threshold = int(failure_threshold)
        self._recovery_timeout = float(recovery_timeout)
        self._half_open_successes = int(half_open_successes)
        self._time_func = time_func
        self._is_failure = is_failure or (lambda _exc: True)

        self._lock = asyncio.Lock()
        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._opened_at: float | None = None
        self._half_open_success_count: int = 0

    def _now(self) -> float:
        return self._time_func()

    @property
    def state(self) -> str:
        return self._state.value

    @property
    def is_open(self) -> bool:
        return self._state is CircuitState.OPEN

    @property
    def is_closed(self) -> bool:
        return self._state is CircuitState.CLOSED

    async def __aenter__(self) -> CircuitBreaker:
        async with self._lock:
            if self._state is CircuitState.OPEN:
                opened = self._opened_at or 0.0
                now = self._now()
                if now - opened >= self._recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_success_count = 0
                else:
                    raise CircuitOpenError("Circuit is open")
        return self

    async def __aexit__(self, exc_type, exc_value, tb) -> bool | None:
        if exc_type is None:
            await self._observation_success()
        elif exc_value is not None and self._is_failure(exc_value):
            await self._observation_failure()
        return False

    async def _observation_success(self) -> None:
        async with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                self._half_open_success_count += 1
                if self._half_open_success_count >= self._half_open_successes:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._opened_at = None
                    self._half_open_success_count = 0
            else:
                self._failure_count = 0

    async def _observation_failure(self) -> None:
        async with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = self._now()
                self._failure_count = 0
                self._half_open_success_count = 0
            else:
                self._failure_count += 1
                if self._failure_count >= self._failure_threshold:
                    self._state = CircuitState.OPEN
                    self._opened_at = self._now()
                    self._failure_count = 0

    async def call(
        self, coro_fn: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any
    ) -> Any:
        """Execute *coro_fn* under circuit protection."""
        async with self:
            return await coro_fn(*args, **kwargs)

    async def reset(self) -> None:
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._opened_at = None
            self._half_open_success_count = 0

    async def force_open(self) -> None:
        async with self._lock:
            self._state = CircuitState.OPEN
            self._opened_at = self._now()
            self._failure_count = 0
            self._half_open_success_count = 0

    async def force_close(self) -> None:
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._opened_at = None
            self._half_open_success_count = 0


# ---------------------------------------------------------------------------
# Decorator-factory style
# ---------------------------------------------------------------------------


class _CircuitBreaker:
    """Stateful circuit breaker bound to one decorated function.

    Not intended for direct use — see the `circuit_breaker` decorator factory.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int,
        recovery_timeout: float,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        # Lock created lazily so it binds to the running event loop
        self._lock: asyncio.Lock | None = None

    @property
    def state(self) -> CircuitState:
        return self._state

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _maybe_transition_to_half_open(self) -> None:
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - (self._last_failure_time or 0.0)
            if elapsed >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                logger.info(
                    "circuit_half_open",
                    extra={"circuit": self.name, "after_seconds": round(elapsed, 1)},
                )

    def _on_success(self) -> None:
        if self._state != CircuitState.CLOSED:
            logger.info("circuit_closed", extra={"circuit": self.name})
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None

    def _on_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if (
            self._failure_count >= self.failure_threshold
            or self._state == CircuitState.HALF_OPEN
        ):
            prev = self._state
            self._state = CircuitState.OPEN
            if prev != CircuitState.OPEN:
                logger.warning(
                    "circuit_opened",
                    extra={"circuit": self.name, "failures": self._failure_count},
                )

    async def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Execute func through the circuit breaker gate.

        Args:
            func: The coroutine function to call.
            *args: Positional arguments forwarded to func.
            **kwargs: Keyword arguments forwarded to func.

        Returns:
            Whatever func returns on success.

        Raises:
            CircuitOpenError: When the circuit is OPEN and the probe window has
                              not yet elapsed.
            Exception: Re-raises any exception raised by func (after observationing
                       the failure).
        """
        lock = self._get_lock()
        async with lock:
            self._maybe_transition_to_half_open()
            if self._state == CircuitState.OPEN:
                raise CircuitOpenError(
                    f"Circuit '{self.name}' is OPEN — call rejected to protect downstream"
                )

        try:
            result = await func(*args, **kwargs)
        except Exception:
            async with lock:
                self._on_failure()
            raise
        else:
            async with lock:
                self._on_success()
            return result


def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
) -> Callable:
    """Decorator factory that wraps an async function with a circuit breaker.

    Args:
        failure_threshold: Consecutive failures before opening the circuit.
        recovery_timeout: Seconds in OPEN state before transitioning to HALF_OPEN.

    Returns:
        Decorator that wraps the target coroutine function.

    Example:
        @circuit_breaker(failure_threshold=5, recovery_timeout=30)
        async def call_external_service(payload: dict) -> None:
            ...  # any exception here is counted as a failure

    Raises:
        CircuitOpenError: When the circuit is OPEN and a call is attempted.
    """

    def decorator(func: Callable) -> Callable:
        breaker = _CircuitBreaker(
            name=getattr(func, "__qualname__", "unnamed_circuit"),
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await breaker.call(func, *args, **kwargs)

        # Expose the breaker instance for inspection / testing
        _attach_circuit_breaker(wrapper, breaker)
        return wrapper

    return decorator
