"""Tests for list cache helpers (Phase 13.4) using fakeredis."""

from __future__ import annotations

import fakeredis.aioredis
import pytest

import services.ingestor.cache as cache_module
from services.ingestor.constants import CACHE_LIST_MAX_LIMIT, CACHE_LIST_MAX_SKIP


@pytest.fixture(autouse=True)
async def fake_redis():
    """Inject a FakeRedis instance as the cache client for every test."""
    client = fakeredis.aioredis.FakeRedis()
    cache_module._client = client
    yield client
    await client.aclose()
    cache_module._client = None


# ── get/set list cache ────────────────────────────────────────────────────────


async def test_set_and_get_records_list() -> None:
    data = [{"id": 1, "source": "alpha"}, {"id": 2, "source": "alpha"}]
    await cache_module.set_records_list("alpha", 0, 10, data)

    result = await cache_module.get_records_list("alpha", 0, 10)
    assert result == data


async def test_get_records_list_miss_returns_none() -> None:
    result = await cache_module.get_records_list("nonexistent", 0, 10)
    assert result is None


async def test_different_params_are_independent_keys() -> None:
    data_a = [{"id": 1}]
    data_b = [{"id": 2}]
    await cache_module.set_records_list("src", 0, 10, data_a)
    await cache_module.set_records_list("src", 0, 20, data_b)

    assert await cache_module.get_records_list("src", 0, 10) == data_a
    assert await cache_module.get_records_list("src", 0, 20) == data_b


# ── skip-cache guard ──────────────────────────────────────────────────────────


async def test_skip_caches_large_skip() -> None:
    data = [{"id": 1}]
    await cache_module.set_records_list("src", CACHE_LIST_MAX_SKIP + 1, 10, data)
    result = await cache_module.get_records_list("src", CACHE_LIST_MAX_SKIP + 1, 10)
    assert result is None


async def test_skip_cache_large_limit() -> None:
    data = [{"id": 1}]
    await cache_module.set_records_list("src", 0, CACHE_LIST_MAX_LIMIT + 1, data)
    result = await cache_module.get_records_list("src", 0, CACHE_LIST_MAX_LIMIT + 1)
    assert result is None


# ── invalidation ──────────────────────────────────────────────────────────────


async def test_invalidate_records_list_by_source_removes_matching_keys() -> None:
    await cache_module.set_records_list("alpha", 0, 10, [{"id": 1}])
    await cache_module.set_records_list("alpha", 0, 20, [{"id": 2}])
    await cache_module.set_records_list("beta", 0, 10, [{"id": 3}])

    await cache_module.invalidate_records_list_by_source("alpha")

    assert await cache_module.get_records_list("alpha", 0, 10) is None
    assert await cache_module.get_records_list("alpha", 0, 20) is None
    # beta should be unaffected
    assert await cache_module.get_records_list("beta", 0, 10) == [{"id": 3}]


async def test_invalidate_source_with_no_keys_is_safe() -> None:
    # Should not raise even when no matching keys exist.
    await cache_module.invalidate_records_list_by_source("ghost_source")


# ── no-op when client is None ─────────────────────────────────────────────────


async def test_get_returns_none_when_no_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache_module, "_client", None)
    result = await cache_module.get_records_list("src", 0, 10)
    assert result is None


async def test_set_is_noop_when_no_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache_module, "_client", None)
    # Should not raise.
    await cache_module.set_records_list("src", 0, 10, [{"id": 1}])


async def test_invalidate_is_noop_when_no_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cache_module, "_client", None)
    await cache_module.invalidate_records_list_by_source("src")
