"""PostgreSQL integration coverage for observation retention."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.config import settings
from services.ingestor.jobs import archive_old_observations
from services.ingestor.models import Observation, ObservationArchive


@pytest.mark.integration
async def test_retention_archives_fidelity_and_is_idempotent_on_postgres(
    postgresql_async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A migrated PostgreSQL schema preserves data before hot-row deletion."""
    db = postgresql_async_session
    now = datetime.now(UTC).replace(tzinfo=None)
    expired = Observation(
        source="retention-integration",
        timestamp=now - timedelta(days=31),
        raw_data={"kind": "expired"},
        tags=["retention", "postgres"],
        processed=True,
        processed_at=now - timedelta(days=30),
        deleted_at=now - timedelta(days=29),
    )
    current = Observation(
        source="retention-integration",
        timestamp=now - timedelta(days=1),
        raw_data={"kind": "current"},
        tags=["retention"],
    )
    db.add_all([expired, current])
    await db.commit()
    expired_id = expired.id

    monkeypatch.setattr(settings, "retention_enabled", True)
    monkeypatch.setattr(settings, "retention_batch_size", 1000)

    first = await archive_old_observations(db, apply=True)
    second = await archive_old_observations(db, apply=True)

    archived = await db.get(ObservationArchive, expired_id)
    assert first["status"] == "applied"
    assert first["eligible"] == 1
    assert first["archived"] == 1
    assert first["deleted"] == 1
    assert first["duration_seconds"] >= 0
    assert second["status"] == "empty"
    assert await db.get(Observation, expired_id) is None
    assert archived is not None
    assert archived.raw_data == {"kind": "expired"}
    assert archived.tags == ["retention", "postgres"]
    assert archived.processed is True
    assert archived.processed_at == expired.processed_at
    assert archived.deleted_at == expired.deleted_at
    assert await db.get(Observation, current.id) is not None
