# libs/resilience — Resilient HTTP client

Provides `AsyncResilientHTTPClient`, a thin aiohttp wrapper backed by `CircuitBreaker`.
The circuit breaker implementation lives in `libs.platform.circuit_breaker`.

## Quick start

```python
from libs.platform.circuit_breaker import CircuitBreaker, circuit_breaker
from libs.resilience.http_client import AsyncResilientHTTPClient, ResilientHTTPError

# --- Class-based (context manager + call()) ---
cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
client = AsyncResilientHTTPClient(circuit_breaker=cb)


async def fetch():
    try:
        resp = await client.get("https://example.local/health")
        return await resp.text()
    except ResilientHTTPError as exc:
        # 5xx response — circuit failure recorded
        raise
    finally:
        await client.close()


# --- Decorator style ---
@circuit_breaker(failure_threshold=5, recovery_timeout=60)
async def call_downstream(payload: dict) -> dict: ...
```

## Testing

`CircuitBreaker` accepts a `time_func` argument so time-based tests are
deterministic without `asyncio.sleep`:

```python
t = [0.0]
cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30, time_func=lambda: t[0])
# ... trigger failures ...
t[0] = 31.0  # advance past recovery_timeout
```

## Full demo

```text
```

Covers: state-machine walkthrough, decorator style, concurrent requests,
and a decision table for when to use each HTTP client option.
