"""Incident notification dispatch and broker enqueue helpers.

Extracted from ``incident_lifecycle`` to break the circular import between
``repositories.contract_drift`` and ``incident_lifecycle``.
"""

from __future__ import annotations

from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from libs.contracts.events import (
    EVENT_NOTIFICATION_DELIVERY_REQUESTED_V1,
    NotificationDeliveryRequestedPayloadV1,
    NotificationDeliveryRequestedV1,
    NotificationTriggerType,
)
from services.ingestor.config import settings
from services.ingestor.core.utils import _aware_utc
from services.ingestor.metrics import dependency_incident_transitions_total
from services.ingestor.notifications import (
    configured_notification_channels,
    dispatch_notification_event,
)
from services.ingestor.repositories.incidents import (
    IncidentTransition,
    mark_notification_attempted,
)
from services.ingestor.repositories.messaging import add_outbox_event


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
                trigger_type=cast("NotificationTriggerType", incident.trigger_type),
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


async def dispatch_incident_transitions(
    db: AsyncSession, transitions: list[IncidentTransition]
) -> None:
    """Dispatch post-commit transitions created by another application flow."""
    await _dispatch_transitions(db, transitions)
