import pytest

from libs.platform.circuit_breaker import CircuitBreaker, CircuitOpenError

pytestmark = pytest.mark.integration


class FakeTime:
    def __init__(self, start: float = 0.0) -> None:
        self.t = float(start)

    def now(self) -> float:  # compatible with time.monotonic
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.mark.asyncio
async def test_trips_open_and_recovers() -> None:
    ft = FakeTime()
    cb = CircuitBreaker(
        failure_threshold=3,
        recovery_timeout=10,
        half_open_successes=1,
        time_func=ft.now,
    )

    async def fail():
        raise RuntimeError("boom")

    async def ok():
        return "ok"

    # trip the breaker
    for _ in range(3):
        with pytest.raises(RuntimeError):
            await cb.call(fail)

    assert cb.is_open

    # before timeout it remains open
    ft.advance(5)
    with pytest.raises(CircuitOpenError):
        await cb.call(ok)

    # after timeout, a trial call succeeds and closes the circuit
    ft.advance(6)
    result = await cb.call(ok)
    assert result == "ok"
    assert cb.is_closed


@pytest.mark.asyncio
async def test_half_open_failure_reopens() -> None:
    ft = FakeTime()
    cb = CircuitBreaker(
        failure_threshold=1, recovery_timeout=5, half_open_successes=1, time_func=ft.now
    )

    async def fail():
        raise RuntimeError("boom")

    # single failure trips immediately
    with pytest.raises(RuntimeError):
        await cb.call(fail)

    assert cb.is_open

    # move to half-open window
    ft.advance(6)

    # trial call fails and breaker re-opens
    with pytest.raises(RuntimeError):
        await cb.call(fail)

    assert cb.is_open
