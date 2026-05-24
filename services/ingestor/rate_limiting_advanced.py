"""Advanced in-memory rate-limiting strategies: token bucket and sliding window.

Why the simple IP-based fixed-window approach (v1) is often insufficient
------------------------------------------------------------------------
Fixed-window (slowapi default) counts requests in a calendar window (e.g., "this
minute").  Two attacks bypass it easily:

1. Window-boundary burst: send 1 000 requests at 00:59 → 0 blocked; send another
   1 000 at 01:01 → 0 blocked.  In 2 seconds the client sent 2 000 requests while
   the limit was supposedly 1 000/min.

2. VPN / shared IPs: a single residential VPN exit node may represent thousands of
   real users.  Blocking the IP blocks everyone behind it, while sophisticated
   clients trivially rotate IPs.

Better algorithms implemented here
------------------------------------
TokenBucketLimiter  — burst-tolerant, smooth throughput guarantee
SlidingWindowLimiter — exact rolling window, eliminates boundary attack

Production note
---------------
Both implementations use in-memory Python dicts.  In a multi-worker deployment
replace the dicts/deques with Redis and atomic Lua scripts (or use
`limits.storage.RedisStorage`).  The *algorithm* stays identical; only the storage
backend changes.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections import defaultdict, deque


RNG = random.SystemRandom()


def apply_jitter(base_value: float, min_jitter: float, max_jitter: float) -> float:
    """Add random jitter to a value to prevent thundering herd.

    Thundering herd problem: many clients hit rate limit simultaneously, receive
    identical Retry-After, and retry at the exact same time → spike.

    Jitter spreads retries across a window, smoothing the load.

    Args:
        base_value: Base retry-after seconds (e.g., from window expiry).
        min_jitter: Minimum random offset to add (e.g., -5s).
        max_jitter: Maximum random offset to add (e.g., +5s).

    Returns:
        base_value + random(min_jitter, max_jitter), clamped to ≥0.
    """
    offset = RNG.uniform(min_jitter, max_jitter)
    return max(0.0, base_value + offset)


class TokenBucketLimiter:
    """Per-key token bucket rate limiter.

    Algorithm
    ---------
    Each client key (IP, user ID, API key…) owns a virtual "bucket" of tokens.

      • Capacity  — maximum tokens the bucket can hold = the burst limit.
      • Refill    — tokens added per second at a steady rate.
      • Consume   — each request costs 1 token.  If the bucket is empty → 429.

    Why it beats fixed-window
    -------------------------
    • No thundering herd at window reset: clients that are idle accumulate tokens
      and can burst, but only up to `capacity`, not 2× the limit.
    • Steady-state throughput is guaranteed: sustained traffic is throttled at
      exactly `refill_per_second` req/s.
    • Bursty but well-behaved clients (e.g., a mobile app that batches n requests)
      are not unfairly penalised.

    Trade-off: burst capacity means the *peak* rate > the *steady* rate, which may
    not be desirable for pricing-sensitive APIs.

    Production swap
    ---------------
    Replace `self._buckets` with a Redis hash and a Lua script that atomically
    reads, refills, and decrements the bucket in a single round-trip.

    Example
    -------
    >>> rl = TokenBucketLimiter(capacity=10, refill_per_second=5 / 60)
    >>> allowed, remaining = await rl.consume("user-42")
    """

    def __init__(self, capacity: int, refill_per_second: float) -> None:
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        # key → (current_tokens: float, last_refill_monotonic: float)
        self._buckets: dict[str, tuple[float, float]] = defaultdict(
            lambda: (float(capacity), time.monotonic())
        )
        self._lock = asyncio.Lock()

    async def consume(self, key: str, tokens: int = 1) -> tuple[bool, float]:
        """Attempt to consume `tokens` from the bucket for `key`.

        Args:
            key: Identifies the rate-limited entity (IP, user ID, API key…).
            tokens: Number of tokens to consume (default 1 per request).

        Returns:
            (allowed, remaining_tokens) — `allowed` is False when the bucket
            is empty; `remaining_tokens` reflects the state *after* this call.
        """
        async with self._lock:
            current, last_refill = self._buckets[key]
            now = time.monotonic()
            elapsed = now - last_refill

            # Refill proportionally to elapsed time, capped at capacity
            current = min(
                float(self.capacity), current + elapsed * self.refill_per_second
            )

            if current >= tokens:
                current -= tokens
                self._buckets[key] = (current, now)
                return True, current
            else:
                self._buckets[key] = (current, now)
                return False, current

    def seconds_until_token(
        self, key: str, min_jitter: float = 0.0, max_jitter: float = 0.0
    ) -> float:
        """Estimate seconds until the next token is available for `key`.

        Useful for the Retry-After response header. Optional jitter prevents
        the thundering herd (multiple clients retrying simultaneously).

        Args:
            key: The rate-limit key.
            min_jitter: Minimum random offset (e.g., -5.0). Default 0 (no jitter).
            max_jitter: Maximum random offset (e.g., +5.0). Default 0 (no jitter).

        Returns:
            Base value + jitter. Pass min_jitter=-5, max_jitter=+5 to spread retries.
        """
        current, last_refill = self._buckets.get(
            key, (float(self.capacity), time.monotonic())
        )
        elapsed = time.monotonic() - last_refill
        current = min(float(self.capacity), current + elapsed * self.refill_per_second)
        deficit = 1.0 - current
        if deficit <= 0:
            return 0.0
        base = deficit / self.refill_per_second
        return apply_jitter(base, min_jitter, max_jitter)


class SlidingWindowLimiter:
    """Per-key sliding (rolling) window rate limiter.

    Algorithm
    ---------
    For each client key, maintain a deque of request timestamps.  On each
    incoming request:

      1. Drop timestamps older than (now - window_seconds)  ← O(evictions)
      2. If len(deque) < limit → allow, append now
      3. Else → deny

    Why it beats fixed-window
    -------------------------
    Fixed-window boundary attack: with a 60-second window and limit=100:

        00:00 - 00:59   → 100 requests (window A fills)
        01:00            window resets
        01:00 - 01:01   → 100 more requests (burst)

    In 2 seconds the client sends 200 requests despite a 100/min limit.
    Sliding window prevents this: the window moves with *now*, so the same
    100 requests at 00:59 are still "in scope" at 01:01.

    Trade-off: higher memory per key (O(limit) timestamps vs O(1) counter for
    fixed window).  For very large limits (e.g., 10 000/hour), a count-based
    approximation (sliding window counter) is preferred.

    Production swap
    ---------------
    Replace `self._windows` with a Redis sorted set (ZRANGEBYSCORE for eviction,
    ZADD for append, ZCARD for count).  A single Lua script makes it atomic.

    Example
    -------
    >>> rl = SlidingWindowLimiter(limit=10, window_seconds=60)
    >>> allowed, remaining = await rl.is_allowed("192.168.1.1")
    """

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        # key → deque of monotonic timestamps for requests in the current window
        self._windows: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def is_allowed(self, key: str) -> tuple[bool, int]:
        """Check whether a request from `key` falls within the rolling window.

        Args:
            key: Identifies the rate-limited entity (IP, user ID, API key…).

        Returns:
            (allowed, remaining) — `remaining` is how many more requests are
            permitted before the window fills.
        """
        async with self._lock:
            now = time.monotonic()
            window = self._windows[key]
            cutoff = now - self.window_seconds

            # Evict timestamps that have scrolled out of the window
            while window and window[0] < cutoff:
                window.popleft()

            current_count = len(window)
            if current_count < self.limit:
                window.append(now)
                return True, self.limit - current_count - 1
            return False, 0

    def reset_in(
        self, key: str, min_jitter: float = 0.0, max_jitter: float = 0.0
    ) -> float:
        """Seconds until the oldest in-window request expires (window slides open).

        Useful for the Retry-After response header. Optional jitter prevents
        the thundering herd (multiple clients retrying simultaneously).

        Args:
            key: The rate-limit key.
            min_jitter: Minimum random offset (e.g., -5.0). Default 0 (no jitter).
            max_jitter: Maximum random offset (e.g., +5.0). Default 0 (no jitter).

        Returns:
            Base value + jitter. Pass min_jitter=-5, max_jitter=+5 to spread retries.
        """
        window = self._windows.get(key)
        if not window:
            return 0.0
        oldest = window[0]
        reset_at = oldest + self.window_seconds
        base = max(0.0, reset_at - time.monotonic())
        return apply_jitter(base, min_jitter, max_jitter)
