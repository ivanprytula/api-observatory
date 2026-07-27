"""Application service joining health samples, incidents, and notifications."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.api_schemas.scorecards import (
    HealthSampleCreate,
    HealthSampleResponse,
)
from services.ingestor.metrics import dependency_incident_transitions_total
from services.ingestor.models import ProviderHealthSample, SourceProfile
from services.ingestor.notifications import dispatch_notification_event
from services.ingestor.repositories.incidents import (
    IncidentTransition,
    mark_notification_attempted,
    reconcile_health_incidents,
)


async def _dispatch_transitions(
    db: AsyncSession, transitions: list[IncidentTransition]
) -> None:
    for transition in transitions:
        incident = transition.incident
        dependency_incident_transitions_total.labels(
            trigger_type=incident.trigger_type,
            transition=transition.transition,
        ).inc()
        if not transition.should_notify:
            continue
        await dispatch_notification_event(
            event="dependency_incident.opened",
            message=incident.summary,
            severity=incident.severity,
            context={
                "incident_id": incident.id,
                "source_id": incident.source_id,
                "tenant_id": incident.tenant_id,
                "trigger_type": incident.trigger_type,
                "occurrence_count": incident.occurrence_count,
                "guidance": incident.guidance,
            },
        )
        await mark_notification_attempted(db, incident)


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
    await db.commit()
    await db.refresh(sample)
    await _dispatch_transitions(db, transitions)
    return HealthSampleResponse.model_validate(sample)


async def dispatch_incident_transitions(
    db: AsyncSession, transitions: list[IncidentTransition]
) -> None:
    """Dispatch post-commit transitions created by another application flow."""
    await _dispatch_transitions(db, transitions)
