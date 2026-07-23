"""Unit coverage for the bounded observation-retention lifecycle."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.config import settings
from services.ingestor.jobs import archive_old_observations
from services.ingestor.models import Observation, ObservationArchive


def _observation(
    source: str, timestamp: datetime, *, deleted: bool = False
) -> Observation:
    return Observation(
        source=source,
        timestamp=timestamp,
        raw_data={"source": source},
        tags=["retention"],
        processed=True,
        processed_at=timestamp,
        deleted_at=timestamp if deleted else None,
    )


async def _count(
    session: AsyncSession, model: type[Observation] | type[ObservationArchive]
) -> int:
    return int((await session.scalar(select(func.count()).select_from(model))) or 0)


@pytest.mark.unit
async def test_retention_dry_run_reports_eligible_rows_without_mutation(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dry runs must report the bounded batch and leave both tables unchanged."""
    now = datetime.now(UTC).replace(tzinfo=None)
    db.add_all(
        [
            _observation("old", now - timedelta(days=31)),
            _observation("new", now - timedelta(days=29)),
        ]
    )
    await db.commit()
    monkeypatch.setattr(settings, "retention_batch_size", 1)

    result = await archive_old_observations(db)

    assert result["status"] == "dry_run"
    assert result["eligible"] == 1
    assert await _count(db, Observation) == 2
    assert await _count(db, ObservationArchive) == 0


@pytest.mark.unit
async def test_retention_apply_requires_explicit_enabled_setting(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An apply request remains non-destructive until the setting is enabled."""
    now = datetime.now(UTC).replace(tzinfo=None)
    db.add(_observation("old", now - timedelta(days=31)))
    await db.commit()
    monkeypatch.setattr(settings, "retention_enabled", False)

    result = await archive_old_observations(db, apply=True)

    assert result["status"] == "disabled"
    assert await _count(db, Observation) == 1
    assert await _count(db, ObservationArchive) == 0


@pytest.mark.unit
async def test_retention_copies_verifies_and_deletes_one_bounded_batch(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Apply copies lifecycle data before deleting only the verified oldest row."""
    now = datetime.now(UTC).replace(tzinfo=None)
    oldest = _observation("oldest", now - timedelta(days=40), deleted=True)
    newer_old = _observation("newer-old", now - timedelta(days=31))
    recent = _observation("recent", now - timedelta(days=1))
    db.add_all([oldest, newer_old, recent])
    await db.commit()
    oldest_id = oldest.id
    monkeypatch.setattr(settings, "retention_enabled", True)
    monkeypatch.setattr(settings, "retention_batch_size", 1)

    result = await archive_old_observations(db, apply=True)

    archived = await db.get(ObservationArchive, oldest_id)
    assert result["status"] == "applied"
    assert result["archived"] == 1
    assert result["deleted"] == 1
    assert await db.get(Observation, oldest_id) is None
    assert archived is not None
    assert archived.source == "oldest"
    assert archived.raw_data == {"source": "oldest"}
    assert archived.tags == ["retention"]
    assert archived.deleted_at == oldest.deleted_at
    assert await _count(db, Observation) == 2


@pytest.mark.unit
async def test_retention_is_idempotent_after_a_successful_apply(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A subsequent run finds no hot observation already archived and deleted."""
    now = datetime.now(UTC).replace(tzinfo=None)
    db.add(_observation("old", now - timedelta(days=31)))
    await db.commit()
    monkeypatch.setattr(settings, "retention_enabled", True)

    first_result = await archive_old_observations(db, apply=True)
    second_result = await archive_old_observations(db, apply=True)

    assert first_result["status"] == "applied"
    assert second_result["status"] == "empty"
    assert await _count(db, Observation) == 0
    assert await _count(db, ObservationArchive) == 1


@pytest.mark.unit
async def test_retention_skips_when_the_distributed_lock_is_held(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only one retention worker may mutate a hot table at a time."""
    now = datetime.now(UTC).replace(tzinfo=None)
    db.add(_observation("old", now - timedelta(days=31)))
    await db.commit()
    monkeypatch.setattr(settings, "retention_enabled", True)

    @asynccontextmanager
    async def held_lock(*_args: object, **_kwargs: object):
        yield False

    monkeypatch.setattr("services.ingestor.cache.redis_lock", held_lock)

    result = await archive_old_observations(db, apply=True)

    assert result["status"] == "lock_held"
    assert result["skipped"] is True
    assert await _count(db, Observation) == 1
    assert await _count(db, ObservationArchive) == 0
