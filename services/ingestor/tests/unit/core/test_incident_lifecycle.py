"""Focused lifecycle tests for dependency incidents."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.scorecards import HealthSampleCreate
from services.ingestor.config import settings
from services.ingestor.incident_lifecycle import record_health_sample
from services.ingestor.models import (
    DependencyIncident,
    ProviderHealthSample,
    SourceProfile,
)


pytestmark = pytest.mark.integration


def _sample(
    source_id: int,
    *,
    minute: int,
    success: bool,
    latency_ms: float,
) -> HealthSampleCreate:
    return HealthSampleCreate(
        source_id=source_id,
        sampled_at=datetime(2026, 7, 24, 12, minute, tzinfo=UTC),
        latency_ms=latency_ms,
        is_success=success,
        http_status=200 if success else 503,
        error_message=None if success else "upstream unavailable",
    )


async def test_health_incidents_deduplicate_and_recover(
    db: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "notification_delivery_mode", "direct")
    dispatch = AsyncMock(return_value={"sent": 0, "failed": 0})
    monkeypatch.setattr(
        "services.ingestor.incident_lifecycle.dispatch_notification_event", dispatch
    )
    source = SourceProfile(
        name="tenant-provider",
        base_url="https://example.com",
        tenant_id=42,
        incident_failure_threshold=2,
        incident_cooldown_seconds=900,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)

    await record_health_sample(
        db, _sample(source.id, minute=0, success=False, latency_ms=25)
    )
    assert await db.scalar(select(DependencyIncident)) is None

    await record_health_sample(
        db, _sample(source.id, minute=1, success=False, latency_ms=30)
    )
    incident = (await db.execute(select(DependencyIncident))).scalar_one()
    assert incident.status == "open"
    assert incident.trigger_type == "availability"
    assert incident.tenant_id == 42
    assert incident.occurrence_count == 1
    assert dispatch.await_count == 1

    await record_health_sample(
        db, _sample(source.id, minute=2, success=False, latency_ms=35)
    )
    await db.refresh(incident)
    assert incident.occurrence_count == 2
    assert dispatch.await_count == 1  # active-incident cooldown suppresses a storm

    await record_health_sample(
        db, _sample(source.id, minute=3, success=True, latency_ms=20)
    )
    await db.refresh(incident)
    assert incident.status == "resolved"
    assert incident.active_key is None
    assert incident.resolved_by == "health-probe-recovery"

    samples = list((await db.execute(select(ProviderHealthSample))).scalars())
    assert {sample.tenant_id for sample in samples} == {42}


async def test_consecutive_latency_breach_opens_and_recovers(
    db: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "notification_delivery_mode", "direct")
    monkeypatch.setattr(
        "services.ingestor.incident_lifecycle.dispatch_notification_event",
        AsyncMock(return_value={"sent": 0, "failed": 0}),
    )
    source = SourceProfile(
        name="slow-provider",
        base_url="https://example.org",
        latency_threshold_ms=100,
        incident_failure_threshold=2,
        incident_cooldown_seconds=0,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)

    await record_health_sample(
        db, _sample(source.id, minute=0, success=True, latency_ms=120)
    )
    await record_health_sample(
        db, _sample(source.id, minute=1, success=True, latency_ms=140)
    )
    incident = (
        await db.execute(
            select(DependencyIncident).where(
                DependencyIncident.trigger_type == "latency"
            )
        )
    ).scalar_one()
    assert incident.status == "open"

    await record_health_sample(
        db, _sample(source.id, minute=2, success=True, latency_ms=80)
    )
    await db.refresh(incident)
    assert incident.status == "resolved"
    assert incident.resolved_at is not None
    assert incident.last_seen_at >= incident.first_seen_at - timedelta(seconds=1)
