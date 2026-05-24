"""Tests for redis_lock context manager (Phase 13.4) using fakeredis."""

from __future__ import annotations

import fakeredis.aioredis
import pytest

import services.ingestor.cache as cache_module
from services.ingestor.cache import redis_lock
from services.ingestor.constants import CACHE_LOCK_PREFIX


@pytest.fixture(autouse=True)
async def fake_redis():
    """Inject FakeRedis as the cache client for every test."""
    client = fakeredis.aioredis.FakeRedis()
    cache_module._client = client
    yield client
    await client.aclose()
    cache_module._client = None


async def test_acquires_lock_when_free() -> None:
    async with redis_lock("test_acquire") as acquired:
        assert acquired is True


async def test_fails_to_acquire_when_held() -> None:
    async with redis_lock("test_contention") as first:
        assert first is True
        # Same key — second attempt should fail
        async with redis_lock("test_contention") as second:
            assert second is False


async def test_lock_released_after_context() -> None:
    async with redis_lock("test_release"):
        pass  # lock should be released when context exits

    # Should be acquirable again
    async with redis_lock("test_release") as acquired:
        assert acquired is True


async def test_lock_key_uses_prefix() -> None:
    lock_name = "my_job"
    expected_key = f"{CACHE_LOCK_PREFIX}:{lock_name}"

    async with redis_lock(lock_name):
        exists = await cache_module._client.exists(expected_key)
        assert exists == 1

    # Released after context
    exists = await cache_module._client.exists(expected_key)
    assert exists == 0


async def test_different_locks_are_independent() -> None:
    async with redis_lock("lock_a") as a:
        async with redis_lock("lock_b") as b:
            assert a is True
            assert b is True


async def test_yields_true_when_no_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without Redis, yield True so jobs still run (fail-open)."""
    monkeypatch.setattr(cache_module, "_client", None)
    async with redis_lock("no_client_lock") as acquired:
        assert acquired is True


async def test_lock_released_on_exception() -> None:
    """Lock must be released even when the protected block raises."""
    with pytest.raises(ValueError):
        async with redis_lock("exc_lock") as acquired:
            assert acquired is True
            raise ValueError("intentional")

    # Lock should be gone
    key = f"{CACHE_LOCK_PREFIX}:exc_lock"
    exists = await cache_module._client.exists(key)
    assert exists == 0
