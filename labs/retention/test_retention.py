"""Unit coverage for the bounded observation-retention lifecycle."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from labs.retention.retention import archive_old_observations  # noqa: E402
from services.ingestor.core.config import settings  # noqa: E402
from services.ingestor.models import (  # noqa: E402
    Observation,
    ObservationArchive,
    SourceProfile,
)


pytestmark = pytest.mark.integration


def _source_profile(name: str = "test-source") -> SourceProfile:
    return SourceProfile(
        name=name,
        base_url=f"https://{name}.example.com",
    )


def _observation(
    source_id: int, timestamp: datetime, *, deleted: bool = False
) -> Observation:
    return Observation(
        source_id=source_id,
        timestamp=timestamp,
        raw_data={"source_id": source_id},
        tags=["retention"],
        processed=True,
        processed_at=timestamp,
        deleted_at=timestamp if deleted else None,
    )


async def _count(
    session: AsyncSession, model: type[Observation] | type[ObservationArchive]
) -> int:
    return int((await session.scalar(select(func.count()).select_from(model))) or 0)


async def test_retention_dry_run_reports_eligible_rows_without_mutation(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dry runs must report the bounded batch and leave both tables unchanged."""
    source = _source_profile("dry-run-source")
    db.add(source)
    await db.flush()
    now = datetime.now(UTC).replace(tzinfo=None)
    db.add_all(
        [
            _observation(source.id, now - timedelta(days=31)),
            _observation(source.id, now - timedelta(days=29)),
        ]
    )
    await db.commit()
    monkeypatch.setattr(settings, "retention_batch_size", 1)

    result = await archive_old_observations(db)

    assert result["status"] == "dry_run"
    assert result["eligible"] == 1
    assert await _count(db, Observation) == 2
    assert await _count(db, ObservationArchive) == 0


async def test_retention_apply_requires_explicit_enabled_setting(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An apply request remains non-destructive until the setting is enabled."""
    source = _source_profile("disabled-source")
    db.add(source)
    await db.flush()
    now = datetime.now(UTC).replace(tzinfo=None)
    db.add(_observation(source.id, now - timedelta(days=31)))
    await db.commit()
    monkeypatch.setattr(settings, "retention_enabled", False)

    result = await archive_old_observations(db, apply=True)

    assert result["status"] == "disabled"
    assert await _count(db, Observation) == 1
    assert await _count(db, ObservationArchive) == 0


async def test_retention_copies_verifies_and_deletes_one_bounded_batch(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Apply copies lifecycle data before deleting only the verified oldest row."""
    source = _source_profile("oldest-source")
    db.add(source)
    await db.flush()
    now = datetime.now(UTC).replace(tzinfo=None)
    oldest = _observation(source.id, now - timedelta(days=40), deleted=True)
    newer_old = _observation(source.id, now - timedelta(days=31))
    recent = _observation(source.id, now - timedelta(days=1))
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
    assert archived.source_id == source.id
    assert archived.raw_data == {"source_id": source.id}
    assert archived.tags == ["retention"]
    assert archived.deleted_at == oldest.deleted_at
    assert await _count(db, Observation) == 2


async def test_retention_is_idempotent_after_a_successful_apply(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A subsequent run finds no hot observation already archived and deleted."""
    source = _source_profile("idempotent-source")
    db.add(source)
    await db.flush()
    now = datetime.now(UTC).replace(tzinfo=None)
    db.add(_observation(source.id, now - timedelta(days=31)))
    await db.commit()
    monkeypatch.setattr(settings, "retention_enabled", True)

    first_result = await archive_old_observations(db, apply=True)
    second_result = await archive_old_observations(db, apply=True)

    assert first_result["status"] == "applied"
    assert second_result["status"] == "empty"
    assert await _count(db, Observation) == 0
    assert await _count(db, ObservationArchive) == 1


async def test_retention_skips_when_the_distributed_lock_is_held(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only one retention worker may mutate a hot table at a time."""
    source = _source_profile("lock-source")
    db.add(source)
    await db.flush()
    now = datetime.now(UTC).replace(tzinfo=None)
    db.add(_observation(source.id, now - timedelta(days=31)))
    await db.commit()
    monkeypatch.setattr(settings, "retention_enabled", True)

    @asynccontextmanager
    async def held_lock(*_args: object, **_kwargs: object):
        yield False

    monkeypatch.setattr("services.ingestor.jobs.retention.redis_lock", held_lock)

    result = await archive_old_observations(db, apply=True)

    assert result["status"] == "lock_held"
    assert result["skipped"] is True
    assert await _count(db, Observation) == 1
    assert await _count(db, ObservationArchive) == 0
