"""PostgreSQL integration coverage for observation retention."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
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


@pytest.mark.integration
async def test_retention_archives_fidelity_and_is_idempotent_on_postgres(
    postgresql_async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A migrated PostgreSQL schema preserves data before hot-row deletion."""
    db = postgresql_async_session
    source = SourceProfile(
        name="retention-integration",
        base_url="https://retention-integration.example.com",
    )
    db.add(source)
    await db.flush()
    now = datetime.now(UTC).replace(tzinfo=None)
    expired = Observation(
        source_id=source.id,
        timestamp=now - timedelta(days=31),
        raw_data={"kind": "expired"},
        tags=["retention", "postgres"],
        processed=True,
        processed_at=now - timedelta(days=30),
        deleted_at=now - timedelta(days=29),
    )
    current = Observation(
        source_id=source.id,
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
