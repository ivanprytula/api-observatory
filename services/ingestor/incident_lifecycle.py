"""Application service joining health samples, incidents, and notifications."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.scorecards import (
    HealthSampleCreate,
    HealthSampleResponse,
)
from services.ingestor.core.incident_notifications import (
    dispatch_incident_transitions,
    enqueue_incident_notification_requests,
)
from services.ingestor.models import ProviderHealthSample, SourceProfile
from services.ingestor.repositories.incidents import (
    reconcile_health_incidents,
)


async def record_health_sample(
    db: AsyncSession, payload: HealthSampleCreate
) -> HealthSampleResponse:
    """Persist a health sample and reconcile incidents in one transaction."""
    source = await db.scalar(
        select(SourceProfile).where(
            SourceProfile.id == payload.source_id,
            SourceProfile.deleted_at.is_(None),
        )
    )
    if source is None:
        raise ValueError("Source not found.")

    sample = ProviderHealthSample(
        source_id=payload.source_id,
        sampled_at=payload.sampled_at.replace(tzinfo=None),
        latency_ms=payload.latency_ms,
        is_success=payload.is_success,
        http_status=payload.http_status,
        response_body_hash=payload.response_body_hash,
        error_message=payload.error_message,
        region=payload.region,
        tenant_id=source.tenant_id,
    )
    db.add(sample)
    await db.flush()
    transitions = await reconcile_health_incidents(db, source=source, sample=sample)
    await enqueue_incident_notification_requests(db, transitions)
    await db.commit()
    await db.refresh(sample)
    await dispatch_incident_transitions(db, transitions)
    return HealthSampleResponse.model_validate(sample)
