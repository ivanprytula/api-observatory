"""External API fetching with retry logic and exponential backoff.

Uses real httpx.AsyncClient to fetch from jsonplaceholder.typicode.com.
Demonstrates resilience patterns: graceful failure, exponential backoff,
timeout handling, and clear error propagation.

Week 4 Phase 2 pattern: Real async HTTP with concurrency control.
"""

import asyncio
import contextlib
import hashlib
import logging
import math
from abc import ABC, abstractmethod

import httpx


logger = logging.getLogger(__name__)

# jsonplaceholder base URL (free, no authentication required)
EXTERNAL_API_BASE = "https://jsonplaceholder.typicode.com"

# Per-event-loop HTTP client management.
#
# httpx.AsyncClient instances are bound to the event loop they were created on.
# Sharing a single client across different asyncio event loops can cause
# ``RuntimeError: Event loop is closed`` when tests/consumers close a loop while a
# client from another loop still exists. To avoid this, we keep a mapping of
# running event loop -> AsyncClient and return the client for the current loop.
#
# `get_http_client()` and `close_http_client()` operate on the current running
# loop only, which is safe for tests that create/close loops per test. This is a
# best-effort approach for cleanup; a `close_all_http_clients()` helper is also
# provided for global shutdown if needed.

# Mapping: event loop -> AsyncClient
_http_clients: dict[asyncio.AbstractEventLoop, httpx.AsyncClient] = {}


async def get_http_client() -> httpx.AsyncClient:
    """Return an AsyncClient associated with the current running event loop.

    Ensures we don't reuse a client created on another event loop which would
    make closing it from the current loop raise ``RuntimeError: Event loop is
    closed``.
    """
    loop = asyncio.get_running_loop()
    client = _http_clients.get(loop)
    if client is not None:
        return client

    client = httpx.AsyncClient(
        timeout=30.0,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )
    _http_clients[loop] = client
    return client


async def close_http_client() -> None:
    """Close the AsyncClient associated with the current running event loop.

    Safe to call multiple times. If there's no running loop (e.g. being called
    from synchronous shutdown), this is a no-op.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop on this thread; nothing to close here.
        return

    client = _http_clients.pop(loop, None)
    if client is None:
        return

    with contextlib.suppress(RuntimeError):
        await client.aclose()


async def close_all_http_clients() -> None:
    """Best-effort close of all tracked AsyncClient instances.

    Iterates over the loop->client mapping and attempts to close each client.
    If the client's loop is different from the current running loop, this will
    schedule the coroutine on that loop using ``asyncio.run_coroutine_threadsafe``
    and wait briefly for completion. Any errors during close are swallowed to
    keep shutdown best-effort.
    """
    # Snapshot keys to avoid mutation during iteration
    loops = list(_http_clients.keys())
    for loop in loops:
        client = _http_clients.pop(loop, None)
        if client is None:
            continue
        try:
            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                current_loop = None

            if current_loop is loop:
                # Close directly on the same loop
                with contextlib.suppress(Exception):
                    await client.aclose()
            elif loop.is_running():
                # Close on the client's loop thread-safely
                try:
                    fut = asyncio.run_coroutine_threadsafe(client.aclose(), loop)
                    # wait a short time for the close to complete
                    fut.result(timeout=1)
                except Exception as e:
                    logger.debug("http_client_cleanup_error", extra={"error": str(e)})
            else:
                # Loop not running; close client directly to avoid resource warning
                try:
                    with contextlib.suppress(Exception):
                        await client.aclose()
                except RuntimeError:
                    # If we can't close it, at least try to prevent resource leak
                    logger.debug("http_client_loop_stopped", extra={"loop": loop})
        except Exception as exc:
            # Best-effort cleanup: never fail caller shutdown path.
            logger.debug("http_client_cleanup_suppressed", extra={"error": str(exc)})


async def fetch_from_external_api(
    url: str,
    simulate_failures: bool = False,
) -> dict:
    """Fetch from external API (jsonplaceholder).

    Args:
        url: Full URL to fetch (e.g., https://jsonplaceholder.typicode.com/posts/1).
        simulate_failures: If True, randomly fail 10% of requests (for testing).

    Returns:
        dict: Parsed JSON response.

    Raises:
        httpx.HTTPError: If request fails (timeout, connection error, 4xx/5xx).
        Exception: If simulate_failures=True and random failure triggered.
    """
    # For testing: simulate 10% random failures
    if simulate_failures:
        import secrets

        if secrets.randbelow(10) == 0:
            raise Exception("Simulated API failure (testing)")

    client = await get_http_client()
    try:
        response = await client.get(url)
        response.raise_for_status()  # Raise on 4xx/5xx
        return response.json()
    except httpx.TimeoutException:
        logger.error("fetch_timeout", extra={"url": url, "error": "Request timeout"})
        raise
    except httpx.HTTPError as e:
        # Only HTTPStatusError has .response; others don't
        status = None
        if isinstance(e, httpx.HTTPStatusError):
            status = e.response.status_code

        logger.error(
            "fetch_http_error",
            extra={
                "url": url,
                "status": status,
                "error": str(e),
            },
        )
        raise


async def fetch_with_retry(
    url: str,
    max_retries: int = 3,
    simulate_failures: bool = False,
) -> dict:
    """Fetch from external API with exponential backoff retry.

    Pattern: Try up to `max_retries` times, waiting 2^attempt seconds between.
    - Attempt 1: immediate
    - Attempt 2: wait 1s, then try
    - Attempt 3: wait 2s, then try
    - Attempt 4: wait 4s, then try
    - If all fail, raise the last exception.

    Args:
        url: API endpoint to fetch from.
        max_retries: Number of retry attempts (default: 3).
        simulate_failures: If True, use simulated 10% failure rate (for testing).

    Returns:
        dict: Response from external API.

    Raises:
        httpx.HTTPError or Exception if all retries exhausted.
    """
    last_exception: Exception | None = None

    for attempt in range(max_retries):
        try:
            logger.info(
                "fetch_attempt",
                extra={"attempt": attempt + 1, "max_retries": max_retries, "url": url},
            )
            result = await fetch_from_external_api(
                url, simulate_failures=simulate_failures
            )
            logger.info(
                "fetch_success",
                extra={"attempt": attempt + 1, "url": url, "retries_used": attempt},
            )
            return result
        except Exception as e:
            last_exception = e

            # If this wasn't the last attempt, wait before retrying
            if attempt < max_retries - 1:
                delay = 2**attempt  # 1s, 2s, 4s...
                logger.warning(
                    "fetch_retry",
                    extra={
                        "attempt": attempt + 1,
                        "url": url,
                        "delay_seconds": delay,
                        "error": str(e),
                    },
                )
                await asyncio.sleep(delay)
            else:
                # Last attempt failed
                logger.error(
                    "fetch_exhausted",
                    extra={
                        "max_retries": max_retries,
                        "url": url,
                        "error": str(e),
                    },
                )

    # All retries exhausted
    if last_exception is not None:
        raise last_exception
    else:
        raise Exception("Unknown error occurred during fetch")


# =============================================================================
# DSA: Bloom Filter  ·  Design Pattern: Strategy
# =============================================================================
#
# Pain diagnosed:
#   fetch_with_retry had no way to skip URLs already fetched in the current
#   scraping run.  Hard-coding a single filter type would make testing harder
#   and algorithm swaps require code edits.
#
# Solution — Strategy pattern:
#   Define UrlSeenStrategy as the abstract interface.  The fetching code depends
#   only on that interface; the concrete implementation is injected or swapped at
#   call-site (Bloom filter for prod, in-memory set for tests, no-op for forced
#   re-fetch mode).
#
# Participants:
#   UrlSeenStrategy      — abstract strategy (is_seen / mark_seen / reset)
#   BitArrayBloomFilter  — concrete strategy: probabilistic, O(m/8) bytes
#   InMemorySetFilter    — concrete strategy: exact, for tests / low cardinality
#   NoOpFilter           — concrete strategy: disabled / forced re-fetch
#
# Data structure — Bloom filter:
#   Space:  O(m) bits, independent of n (number of inserted items)
#   Time:   O(k) per insert/lookup, independent of n
#   Maths:
#     m = ceil(-n · ln(p) / ln(2)²)   optimal bit count
#     k = round(m/n · ln(2))          optimal hash-function count
#   Double-hashing trick (saves k separate hash calls):
#     gᵢ(x) = (h₁(x) + i·h₂(x)) % m   where h₁=SHA-256[:8], h₂=MD5[:8]
#   MD5 is used only for bit-index generation — NOT for security.
# =============================================================================


class UrlSeenStrategy(ABC):
    """Abstract strategy: detect whether a URL was previously requested."""

    @abstractmethod
    def is_seen(self, url: str) -> bool:
        """Return True if the URL was likely seen before (may have false positives)."""

    @abstractmethod
    def mark_seen(self, url: str) -> None:
        """Observation that this URL has been requested."""

    @abstractmethod
    def reset(self) -> None:
        """Clear all seen state (e.g., between scraping runs)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name for logging / metrics labels."""


class BitArrayBloomFilter(UrlSeenStrategy):
    """Hand-rolled Bloom filter backed by a ``bytearray``.

    Probabilistic set: answers "definitely not seen" or "probably seen."
    Never produces false negatives; false-positive rate is configurable.

    Internals::

        capacity=10_000, fp_rate=0.01
          → m = 95,851 bits  (~11.7 KB)
          → k = 7 hash functions
          → double-hashing: gᵢ(x) = (SHA-256[:8] + i·MD5[:8]) % m

    Args:
        capacity:  Expected number of unique URLs to insert.
        fp_rate:   Target false-positive rate (default 1 %).

    Note:
        Not thread-safe; wrap with ``asyncio.Lock`` for concurrent access.
        MD5 used purely for non-security bit-index generation (noqa S324).
    """

    def __init__(self, capacity: int = 10_000, fp_rate: float = 0.01) -> None:
        self._capacity = capacity
        self._fp_rate = fp_rate
        # Derived parameters
        self._m: int = self._optimal_m(capacity, fp_rate)  # total bit count
        self._k: int = self._optimal_k(self._m, capacity)  # hash-function count
        self._bits = bytearray(math.ceil(self._m / 8))  # packed bit array
        self._count: int = 0  # items inserted

    # ------------------------------------------------------------------
    # Bloom filter maths
    # ------------------------------------------------------------------

    @staticmethod
    def _optimal_m(n: int, p: float) -> int:
        """m = ceil(-n · ln(p) / ln(2)²)"""
        return math.ceil(-n * math.log(p) / (math.log(2) ** 2))

    @staticmethod
    def _optimal_k(m: int, n: int) -> int:
        """k = max(1, round(m/n · ln(2)))"""
        return max(1, round((m / n) * math.log(2)))

    # ------------------------------------------------------------------
    # Double-hashing implementation
    # ------------------------------------------------------------------

    def _hash_pair(self, url: str) -> tuple[int, int]:
        """Return two independent 64-bit integers for double-hashing."""
        raw = url.encode("utf-8")
        h1 = int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")
        h2 = int.from_bytes(hashlib.blake2b(raw, digest_size=16).digest()[:8], "big")
        return h1, h2

    def _positions(self, url: str) -> list[int]:
        """Compute k bit positions using the double-hashing trick."""
        h1, h2 = self._hash_pair(url)
        return [(h1 + i * h2) % self._m for i in range(self._k)]

    # ------------------------------------------------------------------
    # Bit manipulation helpers
    # ------------------------------------------------------------------

    def _get_bit(self, pos: int) -> bool:
        byte_idx, bit_idx = divmod(pos, 8)
        return bool(self._bits[byte_idx] & (1 << bit_idx))

    def _set_bit(self, pos: int) -> None:
        byte_idx, bit_idx = divmod(pos, 8)
        self._bits[byte_idx] |= 1 << bit_idx

    # ------------------------------------------------------------------
    # UrlSeenStrategy interface
    # ------------------------------------------------------------------

    def is_seen(self, url: str) -> bool:
        """Return True iff all k bits are set (probably seen)."""
        return all(self._get_bit(p) for p in self._positions(url))

    def mark_seen(self, url: str) -> None:
        """Set all k bits for this URL and increment the item counter."""
        for p in self._positions(url):
            self._set_bit(p)
        self._count += 1

    def reset(self) -> None:
        """Zero all bits — O(m/8) bytes written."""
        self._bits = bytearray(len(self._bits))
        self._count = 0

    @property
    def name(self) -> str:
        return "bloom_filter"

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    @property
    def fill_ratio(self) -> float:
        """Fraction of bits set; should stay below ~0.5 to remain accurate."""
        bits_set = sum(bin(b).count("1") for b in self._bits)
        return bits_set / self._m

    @property
    def item_count(self) -> int:
        """Approximate number of items inserted."""
        return self._count

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"capacity={self._capacity}, fp_rate={self._fp_rate}, "
            f"m={self._m} bits, k={self._k} hashes, "
            f"fill={self.fill_ratio:.2%}, items≈{self._count})"
        )


class InMemorySetFilter(UrlSeenStrategy):
    """Exact URL deduplication via a Python ``set``.

    No false positives; memory usage grows with the number of URLs.
    Preferred for tests and scenarios with low cardinality.
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def is_seen(self, url: str) -> bool:
        return url in self._seen

    def mark_seen(self, url: str) -> None:
        self._seen.add(url)

    def reset(self) -> None:
        self._seen.clear()

    @property
    def name(self) -> str:
        return "in_memory_set"


class NoOpFilter(UrlSeenStrategy):
    """Pass-through strategy — every URL is treated as unseen.

    Use when deduplication is explicitly disabled (e.g., forced re-fetch mode).
    """

    def is_seen(self, url: str) -> bool:  # noqa: ARG002
        return False

    def mark_seen(self, url: str) -> None:  # noqa: ARG002
        pass

    def reset(self) -> None:
        pass

    @property
    def name(self) -> str:
        return "no_op"


# Module-level default strategy — injectable at startup or in tests.
_default_url_filter: UrlSeenStrategy = BitArrayBloomFilter()


def set_url_filter(strategy: UrlSeenStrategy) -> None:
    """Replace the active URL-seen strategy (e.g., swap to InMemorySetFilter in tests)."""
    global _default_url_filter
    _default_url_filter = strategy


def get_url_filter() -> UrlSeenStrategy:
    """Return the currently active URL-seen strategy."""
    return _default_url_filter


async def fetch_dedup(
    url: str,
    *,
    seen_filter: UrlSeenStrategy | None = None,
    max_retries: int = 3,
    simulate_failures: bool = False,
) -> dict | None:
    """Fetch a URL, skipping it when the active strategy says it was already seen.

    Strategy pattern integration: delegates the "have I seen this URL?" decision
    to whichever ``UrlSeenStrategy`` is provided (or the module-level default).
    This keeps the fetch logic unaware of *how* deduplication is done.

    Args:
        url:               Target URL to fetch.
        seen_filter:       Strategy to use; defaults to the module-level filter.
        max_retries:       Retry attempts on failure.
        simulate_failures: If True, inject 10 % random failures for testing.

    Returns:
        Parsed JSON dict on success, or ``None`` if the URL was already seen.
    """
    strategy = seen_filter or _default_url_filter

    if strategy.is_seen(url):
        logger.info(
            "fetch_dedup_skip",
            extra={"url": url, "strategy": strategy.name},
        )
        return None

    result = await fetch_with_retry(
        url, max_retries=max_retries, simulate_failures=simulate_failures
    )
    strategy.mark_seen(url)
    logger.info(
        "fetch_dedup_marked",
        extra={"url": url, "strategy": strategy.name},
    )
    return result
