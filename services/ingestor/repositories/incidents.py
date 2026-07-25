"""Persistence and state transitions for dependency incidents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.models import (
    DependencyIncident,
    ProviderHealthSample,
    SourceProfile,
    _utcnow,
)


ACTIVE_INCIDENT_STATUSES = ("open", "acknowledged")


@dataclass(slots=True)
class IncidentTransition:
    incident: DependencyIncident
    transition: str
    should_notify: bool


def _fingerprint(source: SourceProfile, trigger_type: str) -> str:
    tenant_scope = source.tenant_id if source.tenant_id is not None else "global"
    return f"{tenant_scope}:{source.id}:{trigger_type}"


def _guidance(trigger_type: str) -> str:
    if trigger_type == "availability":
        return (
            "Confirm the failure from an independent request, inspect status/error and "
            "dependency traces, pause risky retries, then verify consecutive recovery probes."
        )
    if trigger_type == "latency":
        return (
            "Compare dependency latency with application and database spans, check saturation "
            "and timeout budgets, then verify recovery below the configured threshold."
        )
    return (
        "Review removed and type-changed fields, compare the provider contract, identify affected "
        "consumers, and use a compatibility or rollback plan before resolving."
    )


def _notification_due(incident: DependencyIncident, *, cooldown_seconds: int) -> bool:
    if incident.last_notification_at is None:
        return True
    return _utcnow() - incident.last_notification_at >= timedelta(
        seconds=cooldown_seconds
    )


async def open_or_update_incident(
    db: AsyncSession,
    *,
    source: SourceProfile,
    trigger_type: str,
    severity: str,
    summary: str,
    details: dict[str, Any],
) -> IncidentTransition:
    """Open one deduplicated incident or update the active occurrence."""
    fingerprint = _fingerprint(source, trigger_type)
    incident = await db.scalar(
        select(DependencyIncident).where(DependencyIncident.active_key == fingerprint)
    )
    now = _utcnow()
    if incident is None:
        incident = DependencyIncident(
            source_id=source.id,
            tenant_id=source.tenant_id,
            trigger_type=trigger_type,
            fingerprint=fingerprint,
            active_key=fingerprint,
            status="open",
            severity=severity,
            summary=summary,
            guidance=_guidance(trigger_type),
            trigger_details=details,
            occurrence_count=1,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(incident)
        await db.flush()
        return IncidentTransition(incident, "opened", True)

    incident.last_seen_at = now
    incident.occurrence_count += 1
    incident.severity = severity
    incident.summary = summary
    incident.trigger_details = details
    return IncidentTransition(
        incident,
        "deduplicated",
        _notification_due(incident, cooldown_seconds=source.incident_cooldown_seconds),
    )


async def resolve_active_incident(
    db: AsyncSession,
    *,
    source: SourceProfile,
    trigger_type: str,
    actor: str,
) -> IncidentTransition | None:
    fingerprint = _fingerprint(source, trigger_type)
    incident = await db.scalar(
        select(DependencyIncident).where(DependencyIncident.active_key == fingerprint)
    )
    if incident is None:
        return None
    now = _utcnow()
    incident.status = "resolved"
    incident.active_key = None
    incident.resolved_at = now
    incident.resolved_by = actor
    incident.last_seen_at = now
    return IncidentTransition(incident, "resolved", False)


async def reconcile_health_incidents(
    db: AsyncSession,
    *,
    source: SourceProfile,
    sample: ProviderHealthSample,
) -> list[IncidentTransition]:
    """Apply availability and latency policies to the latest health sample."""
    threshold = source.incident_failure_threshold
    recent = list(
        (
            await db.execute(
                select(ProviderHealthSample)
                .where(ProviderHealthSample.source_id == source.id)
                .order_by(ProviderHealthSample.sampled_at.desc())
                .limit(threshold)
            )
        )
        .scalars()
        .all()
    )
    transitions: list[IncidentTransition] = []

    consecutive_failures = len(recent) >= threshold and all(
        not item.is_success for item in recent
    )
    if consecutive_failures:
        transitions.append(
            await open_or_update_incident(
                db,
                source=source,
                trigger_type="availability",
                severity="critical",
                summary=f"{threshold} consecutive probes failed for {source.name}.",
                details={
                    "latest_sample_id": sample.id,
                    "http_status": sample.http_status,
                    "error_message": sample.error_message,
                    "threshold": threshold,
                },
            )
        )
    elif sample.is_success:
        resolved = await resolve_active_incident(
            db,
            source=source,
            trigger_type="availability",
            actor="health-probe-recovery",
        )
        if resolved is not None:
            transitions.append(resolved)

    latency_threshold = source.latency_threshold_ms
    if latency_threshold is not None:
        consecutive_slow = len(recent) >= threshold and all(
            item.is_success and item.latency_ms >= latency_threshold for item in recent
        )
        if consecutive_slow:
            transitions.append(
                await open_or_update_incident(
                    db,
                    source=source,
                    trigger_type="latency",
                    severity="warning",
                    summary=(
                        f"{threshold} consecutive probes for {source.name} exceeded "
                        f"{latency_threshold:g} ms."
                    ),
                    details={
                        "latest_sample_id": sample.id,
                        "latency_ms": sample.latency_ms,
                        "threshold_ms": latency_threshold,
                        "consecutive_threshold": threshold,
                    },
                )
            )
        elif sample.is_success and sample.latency_ms < latency_threshold:
            resolved = await resolve_active_incident(
                db,
                source=source,
                trigger_type="latency",
                actor="health-probe-recovery",
            )
            if resolved is not None:
                transitions.append(resolved)

    return transitions


async def list_incidents(
    db: AsyncSession,
    *,
    tenant_id: int | None,
    admin: bool,
    status: str | None,
    source_id: int | None,
    offset: int,
    limit: int,
) -> tuple[list[DependencyIncident], int]:
    base = select(DependencyIncident)
    if not admin:
        base = base.where(DependencyIncident.tenant_id == tenant_id)
    if status is not None:
        base = base.where(DependencyIncident.status == status)
    if source_id is not None:
        base = base.where(DependencyIncident.source_id == source_id)
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                base.order_by(DependencyIncident.last_seen_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), total


async def get_incident(
    db: AsyncSession,
    incident_id: int,
    *,
    tenant_id: int | None,
    admin: bool,
) -> DependencyIncident | None:
    stmt = select(DependencyIncident).where(DependencyIncident.id == incident_id)
    if not admin:
        stmt = stmt.where(DependencyIncident.tenant_id == tenant_id)
    return await db.scalar(stmt)


async def acknowledge_incident(incident: DependencyIncident, *, actor: str) -> None:
    if incident.status != "open":
        raise ValueError("Only an open incident can be acknowledged.")
    incident.status = "acknowledged"
    incident.acknowledged_at = _utcnow()
    incident.acknowledged_by = actor


async def resolve_incident(incident: DependencyIncident, *, actor: str) -> None:
    if incident.status not in ACTIVE_INCIDENT_STATUSES:
        raise ValueError("Only an active incident can be resolved.")
    incident.status = "resolved"
    incident.active_key = None
    incident.resolved_at = _utcnow()
    incident.resolved_by = actor


async def mark_notification_attempted(
    db: AsyncSession, incident: DependencyIncident
) -> None:
    incident.last_notification_at = _utcnow()
    await db.commit()
