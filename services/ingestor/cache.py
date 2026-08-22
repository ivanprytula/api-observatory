"""Async Redis cache layer — fail-open on connection errors.

This module provides a read cache for single-observation lookups. All cache
operations are wrapped in try/except to prevent Redis failures from affecting
the API (fail-open pattern).

Pattern inspired by database.py singleton style:
- Module-level _client singleton
- connect_cache() / disconnect_cache() in lifespan
- All functions are pure async

Observability:
- All cache errors log warnings and increment cache_errors_total counter
- Hits/misses tracked via prometheus counters in metrics.py
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from redis.asyncio import Redis

from services.ingestor.constants import (
    CACHE_KEY_LIST_PREFIX,
    CACHE_KEY_OBSERVATION,
    CACHE_LIST_MAX_LIMIT,
    CACHE_LIST_MAX_SKIP,
    CACHE_LOCK_DEFAULT_TTL_SECONDS,
    CACHE_LOCK_PREFIX,
    CACHE_TTL_LIST,
    CACHE_TTL_OBSERVATION,
)
from services.ingestor.core.utils import redact_url_password


if TYPE_CHECKING:
    from services.ingestor.api_schemas.observations import ObservationResponse


# singleton instance (initialized in lifespan startup)
_client: Redis | None = None


logger = logging.getLogger(__name__)


def get_redis_client() -> Redis | None:
    """Return the connected Cache client for atomic operational primitives."""
    return _client


async def connect_cache(cache_url: str) -> None:
    """Initialize Redis connection.

    Args:
        cache_url: Redis DSN (e.g., redis://localhost:6379/0)

    Raises:
        Exception: If Redis connection fails (will be caught at startup)
    """
    global _client
    _client = Redis.from_url(cache_url, decode_responses=True)
    # Ping to verify connection
    await _client.ping()
    logger.info("cache_connected", extra={"url": redact_url_password(cache_url)})


async def disconnect_cache() -> None:
    """Close Redis connection."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
    logger.info("cache_disconnected")


async def get_observation(observation_id: int) -> ObservationResponse | None:
    """Retrieve a cached observation by ID.

    Args:
        observation_id: Observation primary key

    Returns:
        ObservationResponse if found in cache and valid JSON, else None

    Fails open: returns None on any error (connection, deserialization)
    """
    if _client is None:
        return None

    try:
        from services.ingestor.api_schemas.observations import ObservationResponse

        key = CACHE_KEY_OBSERVATION.format(observation_id=observation_id)
        cached_json = await _client.get(key)
        if cached_json is None:
            return None
        # Deserialize from JSON via Pydantic
        return ObservationResponse.model_validate_json(cached_json)
    except Exception as e:
        logger.warning(
            "cache_get_error",
            extra={"observation_id": observation_id, "error": str(e)},
        )
        from services.ingestor.metrics import cache_errors_total

        cache_errors_total.labels(operation="get").inc()
        return None


async def set_observation(
    observation_id: int,
    observation: ObservationResponse,
    ttl: int = CACHE_TTL_OBSERVATION,
) -> None:
    """Store a observation in cache.

    Args:
        observation_id: Observation primary key
        observation: ObservationResponse instance (will be JSON serialized)
        ttl: Time-to-live in seconds (default: 1 hour)

    Fails open: logs warning + increments error counter on failure
    """
    if _client is None:
        return

    try:
        key = CACHE_KEY_OBSERVATION.format(observation_id=observation_id)
        json_data = observation.model_dump_json()
        await _client.setex(key, ttl, json_data)
        logger.info("cache_set", extra={"observation_id": observation_id, "ttl": ttl})
    except Exception as e:
        logger.warning(
            "cache_set_error",
            extra={"observation_id": observation_id, "error": str(e)},
        )
        from services.ingestor.metrics import cache_errors_total

        cache_errors_total.labels(operation="set").inc()


async def invalidate_observation(observation_id: int) -> None:
    """Delete a cached observation.

    Args:
        observation_id: Observation primary key to invalidate

    Fails open: logs warning + increments error counter on failure
    """
    if _client is None:
        return

    try:
        key = CACHE_KEY_OBSERVATION.format(observation_id=observation_id)
        await _client.delete(key)
        logger.info("cache_invalidate", extra={"observation_id": observation_id})
    except Exception as e:
        logger.warning(
            "cache_invalidate_error",
            extra={"observation_id": observation_id, "error": str(e)},
        )
        from services.ingestor.metrics import cache_errors_total

        cache_errors_total.labels(operation="invalidate").inc()


# ── Phase 13.4: List cache ─────────────────────────────────────────────────


def _list_cache_key(source: str, skip: int, limit: int) -> str:
    """Build list cache key for a paginated query.

    Args:
        source: Observation source name.
        skip: Pagination offset.
        limit: Page size.

    Returns:
        Redis key string.
    """
    return f"{CACHE_KEY_LIST_PREFIX}:{source}:{skip}:{limit}"


def _should_skip_list_cache(skip: int, limit: int) -> bool:
    """Return True when caching the list page would waste memory or miss too often."""
    return skip > CACHE_LIST_MAX_SKIP or limit > CACHE_LIST_MAX_LIMIT


async def get_observations_list(source: str, skip: int, limit: int) -> list | None:
    """Return a cached list of observations for the given source/skip/limit, or None.

    Args:
        source: Observation source filter.
        skip: Pagination offset.
        limit: Page size.

    Returns:
        Deserialized list, or None on cache miss / skip.
    """
    import json

    if _client is None or _should_skip_list_cache(skip, limit):
        return None

    try:
        key = _list_cache_key(source, skip, limit)
        raw = await _client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.warning(
            "cache_list_get_error",
            extra={"source": source, "skip": skip, "limit": limit, "error": str(e)},
        )
        return None


async def set_observations_list(source: str, skip: int, limit: int, data: list) -> None:
    """Persist a paginated list to cache with a short TTL.

    Args:
        source: Observation source filter.
        skip: Pagination offset.
        limit: Page size.
        data: Serialisable list of observation dicts.
    """
    import json

    if _client is None or _should_skip_list_cache(skip, limit):
        return

    try:
        key = _list_cache_key(source, skip, limit)
        await _client.set(key, json.dumps(data), ex=CACHE_TTL_LIST)
    except Exception as e:
        logger.warning(
            "cache_list_set_error",
            extra={"source": source, "skip": skip, "limit": limit, "error": str(e)},
        )


async def invalidate_observations_list_by_source(source: str) -> None:
    """Delete all list cache entries for a given source using SCAN.

    Args:
        source: Source name whose list pages should be evicted.
    """
    if _client is None:
        return

    try:
        pattern = f"{CACHE_KEY_LIST_PREFIX}:{source}:*"
        keys: list[bytes] = []
        async for key in _client.scan_iter(match=pattern, count=100):
            keys.append(key)
        if keys:
            await _client.delete(*keys)
            logger.info(
                "cache_list_invalidated",
                extra={"source": source, "deleted_keys": len(keys)},
            )
    except Exception as e:
        logger.warning(
            "cache_list_invalidate_error",
            extra={"source": source, "error": str(e)},
        )


# ── Phase 13.4: Distributed lock ──────────────────────────────────────────────


@asynccontextmanager
async def redis_lock(
    name: str,
    ttl_seconds: int = CACHE_LOCK_DEFAULT_TTL_SECONDS,
) -> AsyncGenerator[bool]:
    """Async context manager providing a non-blocking distributed lock (SET NX PX).

    Uses a single Redis SET NX PX command — safe and atomic on a single Redis node.
    Does NOT block waiting for the lock; yields ``False`` immediately if not acquired.

    Usage::

        async with redis_lock("job:daily_rollup") as acquired:
            if not acquired:
                return  # another instance holds the lock; skip this run

    Args:
        name: Lock identifier (will be prefixed with ``dp:lock:``).
        ttl_seconds: Lock expiry in seconds (prevents deadlock on crash).

    Yields:
        True if the lock was acquired; False otherwise.
    """
    if _client is None:
        # No Redis — yield True so jobs still run in single-instance deployments.
        yield True
        return

    lock_key = f"{CACHE_LOCK_PREFIX}:{name}"
    acquired = await _client.set(lock_key, "1", nx=True, ex=ttl_seconds)
    try:
        yield bool(acquired)
    finally:
        if acquired:
            try:
                await _client.delete(lock_key)
            except Exception as e:
                logger.warning(
                    "redis_lock_release_error",
                    extra={"lock": name, "error": str(e)},
                )


# =============================================================================
# DSA: Hand-Rolled LRU Cache  ·  Design Pattern: Proxy
# =============================================================================
#
# Pain diagnosed:
#   Redis calls for hot single-observation reads add ~1–3 ms network round-trips each.
#   An in-process Least-Recently-Used cache absorbs the vast majority of repeated
#   lookups with zero I/O.
#
# Solution — Proxy pattern:
#   LruObservationCache implements the same read interface as the module-level Redis
#   functions (get_observation / set_observation / invalidate_observation).  Callers are
#   unaware of whether they are talking to Redis or the in-process proxy —
#   they always call get_observation_with_lru().
#
# Participants:
#   _LruNode           — doubly-linked list node (O(1) splice/remove)
#   LruObservationCache     — concrete proxy: LRU eviction + Redis fallback
#   get_observation_with_lru — public helper that uses the module-level proxy
#
# Data structure — LRU via doubly-linked list + hashmap:
#   get   O(1)  — dict lookup + splice-to-head
#   set   O(1)  — dict insert + prepend; evict tail if full
#   del   O(1)  — dict lookup + splice-out
#   Space O(capacity) nodes + O(capacity) dict entries
# =============================================================================


class _LruNode:
    """Doubly-linked list node holding one cached observation."""

    __slots__ = ("key", "value", "prev", "next")

    def __init__(self, key: int, value: Any) -> None:  # noqa: ANN401
        self.key = key
        self.value = value
        self.prev: _LruNode | None = None
        self.next: _LruNode | None = None


class LruObservationCache:
    """In-process LRU cache — Proxy in front of the Redis observation functions.

        Transparently intercepts ``get_observation`` and ``set_observation`` calls.
    On a cache miss the proxy falls through to Redis and back-fills itself.
    On eviction the entry is simply dropped from memory (Redis remains the SoT).

        Proxy contract:
            ``get_observation_with_lru(id)`` has the same return type as
            ``get_observation(id)`` — callers do not know which layer answered.

        Thread-safety:
            Not thread-safe.  Wrap with ``asyncio.Lock`` for concurrent coroutines.

        Args:
            capacity: Maximum number of observations held in memory simultaneously.
    """

    def __init__(self, capacity: int = 256) -> None:
        self._capacity = capacity
        self._map: dict[int, _LruNode] = {}
        # Sentinel head/tail nodes simplify edge-case handling
        self._head = _LruNode(-1, None)  # most-recently-used side
        self._tail = _LruNode(-2, None)  # least-recently-used side
        self._head.next = self._tail
        self._tail.prev = self._head
        self.hits = 0
        self.misses = 0

    # ------------------------------------------------------------------
    # Doubly-linked list helpers
    # ------------------------------------------------------------------

    def _remove(self, node: _LruNode) -> None:
        """Splice a node out of the list in O(1)."""
        prev, nxt = node.prev, node.next
        if prev is not None:
            prev.next = nxt
        if nxt is not None:
            nxt.prev = prev

    def _prepend(self, node: _LruNode) -> None:
        """Insert a node immediately after the head sentinel (MRU position)."""
        node.prev = self._head
        node.next = self._head.next
        if self._head.next is not None:
            self._head.next.prev = node
        self._head.next = node

    # ------------------------------------------------------------------
    # Public LRU interface
    # ------------------------------------------------------------------

    def get(self, observation_id: int) -> Any | None:
        """Return cached value and promote to MRU, or None on miss."""
        node = self._map.get(observation_id)
        if node is None:
            self.misses += 1
            return None
        # Splice to MRU position
        self._remove(node)
        self._prepend(node)
        self.hits += 1
        return node.value

    def put(self, observation_id: int, value: Any) -> None:
        """Insert or update a observation; evict the LRU entry if over capacity."""
        if observation_id in self._map:
            node = self._map[observation_id]
            node.value = value
            self._remove(node)
            self._prepend(node)
            return

        node = _LruNode(observation_id, value)
        self._map[observation_id] = node
        self._prepend(node)

        if len(self._map) > self._capacity:
            # Evict the tail (LRU) node
            lru = self._tail.prev
            if lru is not None and lru is not self._head:
                self._remove(lru)
                del self._map[lru.key]

    def invalidate(self, observation_id: int) -> None:
        """Remove a specific entry from the in-process cache."""
        node = self._map.pop(observation_id, None)
        if node is not None:
            self._remove(node)

    def clear(self) -> None:
        """Flush all entries (e.g., on app shutdown or test teardown)."""
        self._map.clear()
        self._head.next = self._tail
        self._tail.prev = self._head
        self.hits = 0
        self.misses = 0

    @property
    def size(self) -> int:
        return len(self._map)

    @property
    def hit_ratio(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(capacity={self._capacity}, "
            f"size={self.size}, "
            f"hit_ratio={self.hit_ratio:.2%})"
        )


# Module-level proxy instance (swap in tests via set_lru_cache())
_lru: LruObservationCache = LruObservationCache()


def set_lru_cache(instance: LruObservationCache) -> None:
    """Replace the active LRU proxy (useful in tests to reset state)."""
    global _lru
    _lru = instance


def get_lru_cache() -> LruObservationCache:
    """Return the active LRU proxy instance."""
    return _lru


async def get_observation_with_lru(observation_id: int) -> ObservationResponse | None:
    """Proxy: check LRU first, then fall through to Redis on miss.

    The caller never needs to know which layer answered.

    Args:
        observation_id: Observation primary key.

    Returns:
        ObservationResponse from in-process LRU or Redis, or None on complete miss.
    """
    # 1. Check in-process LRU (zero I/O)
    cached = _lru.get(observation_id)
    if cached is not None:
        logger.debug("lru_hit", extra={"observation_id": observation_id})
        return cached  # type: ignore[return-value]

    # 2. Fall through to Redis
    cache_result = await get_observation(observation_id)
    if cache_result is not None:
        # Back-fill the LRU so the next request is free
        _lru.put(observation_id, cache_result)
        logger.debug("lru_backfill", extra={"observation_id": observation_id})

    return cache_result


async def invalidate_observation_all_layers(observation_id: int) -> None:
    """Invalidate a observation in both the LRU proxy and Redis.

    Call this whenever a observation is updated or deleted so both layers stay
    consistent.  The Proxy contract requires the same interface as plain
    ``invalidate_observation`` so callers don't have to know about the LRU layer.

    Args:
        observation_id: Observation primary key to invalidate.
    """
    _lru.invalidate(observation_id)
    await invalidate_observation(observation_id)
    logger.info(
        "observation_invalidated_all_layers", extra={"observation_id": observation_id}
    )
