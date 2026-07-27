"""Compose existing resilience primitives for one downstream dependency."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from prometheus_client import Counter, Gauge

from libs.platform.bulkhead import AsyncBulkhead, BulkheadRejectedError
from libs.platform.circuit_breaker import CircuitBreaker
from libs.platform.retry import RetryBudget, exponential_backoff


dependency_circuit_breaker_state = Gauge(
    "dependency_circuit_breaker_state",
    "Dependency circuit state (0=closed, 1=open, 2=half_open).",
    ["dependency"],
)
dependency_bulkhead_inflight = Gauge(
    "dependency_bulkhead_inflight",
    "Dependency calls currently admitted by a bulkhead.",
    ["dependency"],
)
dependency_bulkhead_waiting = Gauge(
    "dependency_bulkhead_waiting",
    "Dependency calls waiting for bulkhead admission.",
    ["dependency"],
)
dependency_bulkhead_rejected_total = Counter(
    "dependency_bulkhead_rejected_total",
    "Dependency calls rejected because the bulkhead queue was full.",
    ["dependency"],
)


def is_transient_downstream_error(error: BaseException) -> bool:
    """Return whether an error is safe to retry and should count toward a breaker."""
    if isinstance(error, httpx.TransportError):
        return True

    status_code = getattr(error, "status_code", None)
    response = getattr(error, "response", None)
    if status_code is None:
        status_code = getattr(response, "status_code", None)
    return isinstance(status_code, int) and (status_code == 429 or status_code >= 500)


class DependencyResilience:
    """Bulkhead, breaker, retry budget, and Prometheus state for one dependency."""

    def __init__(
        self,
        name: str,
        *,
        max_concurrency: int,
        max_queue: int,
        retry_budget: RetryBudget | None = None,
    ) -> None:
        self.name = name
        self.breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=30,
            is_failure=is_transient_downstream_error,
        )
        self.bulkhead = AsyncBulkhead(
            name,
            max_concurrency=max_concurrency,
            max_queue=max_queue,
            on_state_change=lambda _bulkhead: self._observe(),
        )
        self._retry_budget = retry_budget
        self._observe()

    async def call(
        self,
        operation: Callable[..., Awaitable[Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Run one outbound operation through all resilience controls."""
        try:
            return await self.bulkhead.run(
                self._call_with_breaker, operation, *args, **kwargs
            )
        except BulkheadRejectedError:
            dependency_bulkhead_rejected_total.labels(dependency=self.name).inc()
            raise
        finally:
            self._observe()

    async def _call_with_breaker(
        self,
        operation: Callable[..., Awaitable[Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        async def breaker_protected_operation(
            *call_args: Any, **call_kwargs: Any
        ) -> Any:
            return await self.breaker.call(operation, *call_args, **call_kwargs)

        retrying_operation = exponential_backoff(
            max_retries=1,
            base_delay=0.25,
            max_delay=0.25,
            retry_budget=self._retry_budget,
            retry_if=is_transient_downstream_error,
        )(breaker_protected_operation)
        return await retrying_operation(*args, **kwargs)

    def _observe(self) -> None:
        state_value = {"closed": 0, "open": 1, "half_open": 2}[self.breaker.state]
        dependency_circuit_breaker_state.labels(dependency=self.name).set(state_value)
        dependency_bulkhead_inflight.labels(dependency=self.name).set(
            self.bulkhead.inflight
        )
        dependency_bulkhead_waiting.labels(dependency=self.name).set(
            self.bulkhead.waiting
        )
