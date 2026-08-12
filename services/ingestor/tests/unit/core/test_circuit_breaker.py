import asyncio

import pytest

from libs.platform.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    circuit_breaker,
)


class FakeTime:
    def __init__(self, start: float = 0.0) -> None:
        self.t = float(start)

    def now(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.mark.unit
async def test_direct_breaker_recovers_with_injected_clock() -> None:
    """The concrete breaker transitions without waiting on wall-clock time."""
    clock = FakeTime()
    breaker = CircuitBreaker(
        failure_threshold=1,
        recovery_timeout=5,
        half_open_successes=1,
        time_func=clock.now,
    )

    async def fail() -> None:
        raise RuntimeError("boom")

    async def succeed() -> str:
        return "ok"

    with pytest.raises(RuntimeError, match="boom"):
        await breaker.call(fail)
    assert breaker.is_open

    clock.advance(6)
    assert await breaker.call(succeed) == "ok"
    assert breaker.is_closed


@pytest.mark.unit
async def test_circuit_opens_after_threshold():
    """Circuit opens after failure_threshold consecutive failures."""
    call_count = 0

    @circuit_breaker(failure_threshold=3, recovery_timeout=1.0)
    async def flaky_function():
        nonlocal call_count
        call_count += 1
        raise ValueError("forced failure")

    # First 3 calls fail, circuit still closed (but counting)
    for _ in range(3):
        with pytest.raises(ValueError):
            await flaky_function()

    # 4th call rejected by open circuit
    with pytest.raises(CircuitOpenError):
        await flaky_function()

    assert flaky_function._circuit_breaker.state == CircuitState.OPEN
    assert call_count == 3  # Function not called when circuit open


@pytest.mark.unit
async def test_circuit_half_open_after_timeout():
    """Circuit transitions to HALF_OPEN after recovery_timeout."""

    @circuit_breaker(failure_threshold=2, recovery_timeout=0.1)
    async def flaky_function():
        raise ValueError("fail")

    # Open the circuit
    for _ in range(2):
        with pytest.raises(ValueError):
            await flaky_function()

    assert flaky_function._circuit_breaker.state == CircuitState.OPEN

    # Wait for recovery timeout
    await asyncio.sleep(0.15)

    # Next call should be attempted (HALF_OPEN state internally)
    # but will fail again and re-open
    with pytest.raises(ValueError):
        await flaky_function()

    # Circuit re-opens after HALF_OPEN failure
    assert flaky_function._circuit_breaker.state == CircuitState.OPEN


@pytest.mark.unit
async def test_circuit_closes_on_success_in_half_open():
    """Circuit closes when a call succeeds in HALF_OPEN state."""
    fail_next = True

    @circuit_breaker(failure_threshold=2, recovery_timeout=0.1)
    async def sometimes_fails():
        nonlocal fail_next
        if fail_next:
            raise ValueError("fail")
        return "success"

    # Open the circuit
    for _ in range(2):
        with pytest.raises(ValueError):
            await sometimes_fails()

    # Wait for HALF_OPEN
    await asyncio.sleep(0.15)

    # Success closes the circuit
    fail_next = False
    result = await sometimes_fails()
    assert result == "success"
    assert sometimes_fails._circuit_breaker.state == CircuitState.CLOSED


@pytest.mark.unit
async def test_success_resets_failure_count():
    """Successful call in CLOSED state resets failure counter."""
    should_fail = True

    @circuit_breaker(failure_threshold=5, recovery_timeout=1.0)
    async def intermittent():
        if should_fail:
            raise ValueError("fail")
        return "success"

    # 3 failures
    for _ in range(3):
        with pytest.raises(ValueError):
            await intermittent()

    # 1 success — resets counter
    should_fail = False
    result = await intermittent()
    assert result == "success"
    assert intermittent._circuit_breaker.state == CircuitState.CLOSED
    assert intermittent._circuit_breaker._failure_count == 0

    # Now fail 5 times (threshold) to verify circuit opens
    should_fail = True
    for _ in range(5):
        with pytest.raises(ValueError):
            await intermittent()

    # Circuit opens after hitting threshold
    assert intermittent._circuit_breaker.state == CircuitState.OPEN

    # Next call is rejected
    with pytest.raises(CircuitOpenError):
        await intermittent()


@pytest.mark.unit
async def test_circuit_open_error_message():
    """CircuitOpenError includes the circuit name in the message."""

    @circuit_breaker(failure_threshold=1, recovery_timeout=1.0)
    async def failing_func():
        raise ValueError("fail")

    # Open the circuit
    with pytest.raises(ValueError):
        await failing_func()

    # Next call raises CircuitOpenError with name
    with pytest.raises(CircuitOpenError) as exc_info:
        await failing_func()

    assert "failing_func" in str(exc_info.value)
    assert "OPEN" in str(exc_info.value)


@pytest.mark.unit
async def test_concurrent_calls_thread_safe():
    """Circuit breaker state transitions are safe under concurrent access."""
    call_count = 0

    @circuit_breaker(failure_threshold=10, recovery_timeout=1.0)
    async def concurrent_fail():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.01)  # Simulate I/O
        raise ValueError("fail")

    # Launch 20 concurrent calls
    tasks = [concurrent_fail() for _ in range(20)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # All calls before threshold should fail with ValueError
    # Calls at/after threshold may get CircuitOpenError
    value_errors = [r for r in results if isinstance(r, ValueError)]
    circuit_errors = [r for r in results if isinstance(r, CircuitOpenError)]

    # At least 10 should have been attempted (failure_threshold=10)
    assert call_count >= 10
    assert len(value_errors) >= 10
    # Some may have hit the open circuit
    assert len(value_errors) + len(circuit_errors) == 20


@pytest.mark.unit
async def test_circuit_opens_on_half_open_failure():
    """HALF_OPEN state re-opens circuit immediately on first failure."""

    @circuit_breaker(failure_threshold=2, recovery_timeout=0.1)
    async def flaky():
        raise ValueError("still broken")

    # Open circuit
    for _ in range(2):
        with pytest.raises(ValueError):
            await flaky()

    assert flaky._circuit_breaker.state == CircuitState.OPEN

    # Wait for recovery
    await asyncio.sleep(0.15)

    # HALF_OPEN: one failure re-opens
    with pytest.raises(ValueError):
        await flaky()

    assert flaky._circuit_breaker.state == CircuitState.OPEN


@pytest.mark.unit
async def test_multiple_successes_in_closed_state():
    """Circuit stays closed on repeated successes."""

    @circuit_breaker(failure_threshold=5, recovery_timeout=1.0)
    async def always_works():
        return "ok"

    for _ in range(100):
        result = await always_works()
        assert result == "ok"

    assert always_works._circuit_breaker.state == CircuitState.CLOSED
    assert always_works._circuit_breaker._failure_count == 0


@pytest.mark.unit
async def test_independent_circuit_breakers():
    """Each decorated function gets its own circuit breaker instance."""

    @circuit_breaker(failure_threshold=2, recovery_timeout=1.0)
    async def func_a():
        raise ValueError("a fails")

    @circuit_breaker(failure_threshold=2, recovery_timeout=1.0)
    async def func_b():
        raise ValueError("b fails")

    # Open circuit A
    for _ in range(2):
        with pytest.raises(ValueError):
            await func_a()

    # Circuit A is open, B is still closed
    assert func_a._circuit_breaker.state == CircuitState.OPEN
    assert func_b._circuit_breaker.state == CircuitState.CLOSED

    # B can still be called
    for _ in range(2):
        with pytest.raises(ValueError):
            await func_b()

    # Now both open
    assert func_a._circuit_breaker.state == CircuitState.OPEN
    assert func_b._circuit_breaker.state == CircuitState.OPEN


@pytest.mark.unit
async def test_recovery_timeout_zero():
    """recovery_timeout=0 means circuit recovers immediately."""

    @circuit_breaker(failure_threshold=2, recovery_timeout=0.0)
    async def instant_recovery():
        raise ValueError("fail")

    # Open circuit
    for _ in range(2):
        with pytest.raises(ValueError):
            await instant_recovery()

    assert instant_recovery._circuit_breaker.state == CircuitState.OPEN

    # No sleep needed — next call is HALF_OPEN
    # (will fail and re-open, but proves HALF_OPEN transition worked)
    with pytest.raises(ValueError):
        await instant_recovery()
