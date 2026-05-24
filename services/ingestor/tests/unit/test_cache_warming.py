"""Tests for startup cache warming (Phase 13.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TypedDict

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.ingestor.database import Base
from services.ingestor.models import Record
from services.ingestor.services_lifecycle import _warm_list_cache


class WarmCall(TypedDict):
    """Captured args passed to set_records_list during warmup."""

    source: str
    skip: int
    limit: int
    size: int


@pytest.fixture
async def session_factory_fixture():
    """Provide an in-memory SQLite async session factory with schema created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_warm_list_cache_populates_top_sources(
    monkeypatch: pytest.MonkeyPatch,
    session_factory_fixture: async_sessionmaker,
) -> None:
    """Warm task should cache page 1 for most active sources."""
    now = datetime.now(UTC).replace(tzinfo=None)

    async with session_factory_fixture() as session:
        # alpha has highest volume, then beta, then gamma
        session.add_all(
            [
                Record(
                    source="alpha",
                    timestamp=now - timedelta(minutes=1),
                    raw_data={"n": 1},
                    tags=["a"],
                ),
                Record(
                    source="alpha",
                    timestamp=now - timedelta(minutes=2),
                    raw_data={"n": 2},
                    tags=["a"],
                ),
                Record(
                    source="alpha",
                    timestamp=now - timedelta(minutes=3),
                    raw_data={"n": 3},
                    tags=["a"],
                ),
                Record(
                    source="beta",
                    timestamp=now - timedelta(minutes=4),
                    raw_data={"n": 4},
                    tags=["b"],
                ),
                Record(
                    source="beta",
                    timestamp=now - timedelta(minutes=5),
                    raw_data={"n": 5},
                    tags=["b"],
                ),
                Record(
                    source="gamma",
                    timestamp=now - timedelta(minutes=6),
                    raw_data={"n": 6},
                    tags=["g"],
                ),
            ]
        )
        await session.commit()

    monkeypatch.setattr(
        "services.ingestor.database.AsyncSessionLocal", session_factory_fixture
    )

    calls: list[WarmCall] = []

    async def fake_set_records_list(
        source: str, skip: int, limit: int, data: list
    ) -> None:
        calls.append(
            {
                "source": source,
                "skip": skip,
                "limit": limit,
                "size": len(data),
            }
        )

    monkeypatch.setattr(
        "services.ingestor.cache.set_records_list", fake_set_records_list
    )

    await _warm_list_cache()

    assert calls
    assert calls[0]["source"] == "alpha"
    assert {c["source"] for c in calls} == {"alpha", "beta", "gamma"}
    for call in calls:
        assert call["skip"] == 0
        assert call["limit"] == 100
        assert call["size"] >= 1


async def test_warm_list_cache_fails_open_on_query_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Warm task should not raise when DB/session lookup fails."""

    class BrokenSessionFactory:
        def __call__(self):
            raise RuntimeError("db unavailable")

    monkeypatch.setattr(
        "services.ingestor.database.AsyncSessionLocal", BrokenSessionFactory()
    )

    # Should not raise.
    await _warm_list_cache()
