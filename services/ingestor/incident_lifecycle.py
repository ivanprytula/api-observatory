"""Application service joining health samples, incidents, and notifications."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.contracts.events import (
    EVENT_NOTIFICATION_DELIVERY_REQUESTED_V1,
    NotificationDeliveryRequestedPayloadV1,
    NotificationDeliveryRequestedV1,
)
from services.ingestor.api_schemas.scorecards import (
    HealthSampleCreate,
    HealthSampleResponse,
)
from services.ingestor.config import settings
from services.ingestor.metrics import dependency_incident_transitions_total
from services.ingestor.models import ProviderHealthSample, SourceProfile
from services.ingestor.notifications import (
    configured_notification_channels,
    dispatch_notification_event,
)
from services.ingestor.repositories.incidents import (
    IncidentTransition,
    mark_notification_attempted,
    reconcile_health_incidents,
)
from services.ingestor.repositories.messaging import add_outbox_event


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _notification_message_id(transition: IncidentTransition) -> str:
    incident = transition.incident
    return f"incident:{incident.id}:notification:{incident.occurrence_count}"


async def enqueue_incident_notification_requests(
    db: AsyncSession,
    transitions: list[IncidentTransition],
) -> None:
    """Add broker requests to the caller-owned incident transaction."""
    if (
        settings.notification_delivery_mode != "broker"
        or not settings.notifications_enabled
    ):
        return

    channels = configured_notification_channels()
    if not channels:
        raise ValueError(
            "Broker notification delivery requires at least one valid default channel."
        )

    for transition in transitions:
        if not transition.should_notify:
            continue
        incident = transition.incident
        message_id = _notification_message_id(transition)
        event = NotificationDeliveryRequestedV1(
            message_id=message_id,
            occurred_at=_aware_utc(incident.last_seen_at),
            payload=NotificationDeliveryRequestedPayloadV1(
                incident_id=incident.id,
                source_id=incident.source_id,
                tenant_id=incident.tenant_id,
                severity=incident.severity,
                summary=incident.summary,
                trigger_type=incident.trigger_type,
                occurrence_count=incident.occurrence_count,
                guidance=incident.guidance,
                channels=channels,
            ),
        )
        await add_outbox_event(
            db,
            aggregate_type="dependency_incident",
            aggregate_id=str(incident.id),
            event_type=EVENT_NOTIFICATION_DELIVERY_REQUESTED_V1,
            payload=event.model_dump(mode="json"),
            idempotency_key=f"notification-request:{message_id}",
            tenant_id=incident.tenant_id,
        )
        incident.last_notification_at = incident.last_seen_at


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
        if settings.notification_delivery_mode == "broker":
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
    await enqueue_incident_notification_requests(db, transitions)
    await db.commit()
    await db.refresh(sample)
    await _dispatch_transitions(db, transitions)
    return HealthSampleResponse.model_validate(sample)


async def dispatch_incident_transitions(
    db: AsyncSession, transitions: list[IncidentTransition]
) -> None:
    """Dispatch post-commit transitions created by another application flow."""
    await _dispatch_transitions(db, transitions)
