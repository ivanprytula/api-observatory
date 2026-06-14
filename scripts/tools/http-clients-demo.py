"""
Demo: Resilient HTTP client — CircuitBreaker + AsyncResilientHTTPClient

Covers:
  1. CircuitBreaker standalone — state-machine walkthrough (no network needed)
  2. circuit_breaker decorator — wraps any async function
  3. AsyncResilientHTTPClient — aiohttp + circuit breaker against a real API
  4. Concurrent resilient requests — asyncio.gather with shared breaker
  5. httpx vs aiohttp vs resilient client — when to use what

Run:
    uv run python scripts/tools/http-clients-demo.py
"""

import asyncio
import logging
import sys
import time
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger(__name__)

_SEP = "─" * 68

# ---------------------------------------------------------------------------
# Demo 1: CircuitBreaker standalone — no network required
# ---------------------------------------------------------------------------


async def demo_circuit_state_machine() -> None:
    """Walk through CLOSED → OPEN → HALF_OPEN → CLOSED without any real I/O."""
    from libs.platform.circuit_breaker import CircuitBreaker, CircuitOpenError

    logger.info(_SEP)
    logger.info("DEMO 1 — CircuitBreaker state machine (offline, injected time)")
    logger.info(_SEP)

    t = [0.0]

    cb = CircuitBreaker(
        failure_threshold=3,
        recovery_timeout=30.0,
        half_open_successes=1,
        time_func=lambda: t[0],
    )
    logger.info(f"Initial state: {cb.state}")  # closed

    # Three consecutive failures trip the breaker
    for i in range(1, 4):
        try:
            async with cb:
                raise RuntimeError("downstream unavailable")
        except RuntimeError:
            pass
        logger.info(f"After failure #{i}: {cb.state}")

    # Next call is rejected immediately — circuit is OPEN
    try:
        async with cb:
            pass
    except CircuitOpenError:
        logger.info("Call rejected (CircuitOpenError) — circuit is OPEN ✓")

    # Advance simulated clock past recovery_timeout
    t[0] = 31.0
    logger.info("Clock advanced to t=31 s (past recovery_timeout=30 s)")

    # First probe in HALF_OPEN succeeds → CLOSED
    async with cb:
        logger.info("Probe call allowed — state during call: half_open")
    logger.info(f"After successful probe: {cb.state}")  # closed
    logger.info("")


# ---------------------------------------------------------------------------
# Demo 2: circuit_breaker decorator
# ---------------------------------------------------------------------------


async def demo_decorator_style() -> None:
    """Show the @circuit_breaker decorator wrapping an async function."""
    from libs.platform.circuit_breaker import CircuitOpenError, circuit_breaker

    logger.info(_SEP)
    logger.info("DEMO 2 — @circuit_breaker decorator")
    logger.info(_SEP)

    call_count = 0

    @circuit_breaker(failure_threshold=2, recovery_timeout=1.0)
    async def flaky_downstream() -> str:
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise ConnectionError(f"timeout on attempt {call_count}")
        return "ok"

    # Two failures open the circuit
    for attempt in range(1, 3):
        try:
            await flaky_downstream()
        except ConnectionError as exc:
            logger.info(f"Attempt {attempt} failed: {exc}")

    # Third call is short-circuited
    try:
        await flaky_downstream()
    except CircuitOpenError:
        logger.info("Call short-circuited by open circuit ✓")

    # Wait for recovery window then succeed
    logger.info("Waiting 1.1 s for recovery_timeout …")
    await asyncio.sleep(1.1)
    result = await flaky_downstream()
    logger.info(f"Recovered — got: {result!r} ✓\n")


# ---------------------------------------------------------------------------
# Demo 3: AsyncResilientHTTPClient against a real public API
# ---------------------------------------------------------------------------

_API = "https://jsonplaceholder.typicode.com"


async def demo_resilient_http_client() -> None:
    """AsyncResilientHTTPClient + CircuitBreaker against jsonplaceholder."""
    from libs.platform.circuit_breaker import CircuitBreaker
    from libs.resilience.http_client import AsyncResilientHTTPClient, ResilientHTTPError

    logger.info(_SEP)
    logger.info("DEMO 3 — AsyncResilientHTTPClient (aiohttp + CircuitBreaker)")
    logger.info(_SEP)

    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)
    client = AsyncResilientHTTPClient(circuit_breaker=cb)

    try:
        resp = await client.get(f"{_API}/posts/1")
        data = await resp.json()
        logger.info(f"GET /posts/1  → {resp.status}  title={data['title']!r}")

        resp = await client.get(f"{_API}/users/1")
        user = await resp.json()
        logger.info(f"GET /users/1  → {resp.status}  name={user['name']!r}")

        # POST example
        resp = await client.post(
            f"{_API}/posts",
            json={"title": "resilience demo", "body": "circuit is closed", "userId": 1},
        )
        created = await resp.json()
        logger.info(f"POST /posts   → {resp.status}  id={created['id']}")

    except ResilientHTTPError as exc:
        logger.error(f"HTTP error {exc.status}: {exc.body}")
    finally:
        await client.close()
        logger.info(f"Circuit state after clean run: {cb.state}\n")


# ---------------------------------------------------------------------------
# Demo 4: Concurrent resilient requests — shared CircuitBreaker
# ---------------------------------------------------------------------------


async def demo_concurrent_resilient() -> None:
    """Fire multiple requests in parallel under one shared CircuitBreaker."""
    from libs.platform.circuit_breaker import CircuitBreaker
    from libs.resilience.http_client import AsyncResilientHTTPClient

    logger.info(_SEP)
    logger.info("DEMO 4 — Concurrent requests with shared CircuitBreaker")
    logger.info(_SEP)

    cb = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)
    client = AsyncResilientHTTPClient(circuit_breaker=cb)

    try:
        t0 = time.monotonic()
        resps = await asyncio.gather(
            *[client.get(f"{_API}/posts/{i}") for i in range(1, 6)]
        )
        elapsed = time.monotonic() - t0
        titles = [await r.json() for r in resps]
        logger.info(
            f"5 concurrent GETs completed in {elapsed:.2f} s "
            f"— circuit state: {cb.state}"
        )
        for t in titles:
            logger.info(f"  post {t['id']:>2}: {t['title'][:55]}")
    finally:
        await client.close()
        logger.info("")


# ---------------------------------------------------------------------------
# Demo 5: When to use what — decision table
# ---------------------------------------------------------------------------


def demo_decision_table() -> None:
    logger.info(_SEP)
    logger.info("DEMO 5 — Which HTTP client to use?")
    logger.info(_SEP)
    print(
        """
┌─────────────────────────────────┬────────────────────────────────────────────┐
│ Need                            │ Use                                        │
├─────────────────────────────────┼────────────────────────────────────────────┤
│ Simple one-off scripts / tests  │ httpx.AsyncClient (requests-like API)      │
│ Fine-grained timeout control    │ aiohttp.ClientSession (per-phase timeouts) │
│ Production service call         │ AsyncResilientHTTPClient (CB + aiohttp)    │
│ Protect any async function      │ @circuit_breaker decorator                 │
│ Manual gate (context manager)   │ CircuitBreaker (async with cb:)            │
└─────────────────────────────────┴────────────────────────────────────────────┘

Canonical import paths (as of Phase 14):
  from libs.platform.circuit_breaker import CircuitBreaker, circuit_breaker
  from libs.resilience.http_client   import AsyncResilientHTTPClient
"""
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    logger.info("=" * 68)
    logger.info("  Resilient HTTP Client Demo — libs.platform + libs.resilience")
    logger.info("=" * 68 + "\n")

    demo_decision_table()
    await demo_circuit_state_machine()
    await demo_decorator_style()
    await demo_resilient_http_client()
    await demo_concurrent_resilient()

    logger.info("=" * 68)
    logger.info("  ALL DEMOS COMPLETE ✓")
    logger.info("=" * 68)


if __name__ == "__main__":
    asyncio.run(main())
