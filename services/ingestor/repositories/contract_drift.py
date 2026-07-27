"""Async CRUD and drift detection logic for contract snapshots."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor import pubsub
from services.ingestor.api_schemas.contract_drift import (
    CompatibilityReportResponse,
    ContractSnapshotCreate,
)
from services.ingestor.constants import (
    CONTRACT_COMPATIBILITY_MAX_SCORE,
    CONTRACT_COMPATIBILITY_MIN_SCORE,
    CONTRACT_PENALTY_ADDED_FIELD,
    CONTRACT_PENALTY_REMOVED_FIELD,
    CONTRACT_PENALTY_TYPE_CHANGE,
)
from services.ingestor.models import (
    AgentRun,
    ContractSnapshot,
    DriftEvent,
    Observation,
    SourceProfile,
    _utcnow,
)
from services.ingestor.repositories.incidents import (
    IncidentTransition,
    open_or_update_incident,
)


logger = logging.getLogger(__name__)


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _flatten_schema(payload: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in payload.items():
        path = f"{prefix}.{key}" if prefix else key
        value_type = _value_type(value)

        if isinstance(value, dict):
            # Observation the parent node type so scalar<->object transitions are visible.
            flat[path] = value_type
            if value:
                flat.update(_flatten_schema(value, path))
        else:
            flat[path] = value_type

    return flat


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _diff_contract(
    previous_flat: dict[str, str],
    current_flat: dict[str, str],
) -> tuple[list[str], list[str], dict[str, dict[str, str]]]:
    added = sorted([k for k in current_flat if k not in previous_flat])
    removed = sorted([k for k in previous_flat if k not in current_flat])

    type_changed: dict[str, dict[str, str]] = {}
    shared = set(previous_flat).intersection(current_flat)
    for key in sorted(shared):
        if previous_flat[key] != current_flat[key]:
            type_changed[key] = {
                "from_type": previous_flat[key],
                "to_type": current_flat[key],
            }

    return added, removed, type_changed


def _compatibility_score(
    added_fields: list[str],
    removed_fields: list[str],
    type_changed_fields: dict[str, dict[str, str]],
) -> float:
    score = CONTRACT_COMPATIBILITY_MAX_SCORE
    score -= len(added_fields) * CONTRACT_PENALTY_ADDED_FIELD
    score -= len(removed_fields) * CONTRACT_PENALTY_REMOVED_FIELD
    score -= len(type_changed_fields) * CONTRACT_PENALTY_TYPE_CHANGE
    return max(CONTRACT_COMPATIBILITY_MIN_SCORE, round(score, 2))


def _event_type(
    added_fields: list[str],
    removed_fields: list[str],
    type_changed_fields: dict[str, dict[str, str]],
) -> str:
    if removed_fields or type_changed_fields:
        return "breaking"
    if added_fields:
        return "non_breaking"
    return "none"


def _severity(event_type: str, score: float) -> str:
    if event_type == "none":
        return "none"
    if score >= 90.0:
        return "low"
    if score >= 75.0:
        return "medium"
    if score >= 50.0:
        return "high"
    return "critical"


def _summary(
    event_type: str,
    added_fields: list[str],
    removed_fields: list[str],
    type_changed_fields: dict[str, dict[str, str]],
) -> str:
    if event_type == "none":
        return "No schema drift detected."

    parts: list[str] = []
    if added_fields:
        parts.append(f"added={len(added_fields)}")
    if removed_fields:
        parts.append(f"removed={len(removed_fields)}")
    if type_changed_fields:
        parts.append(f"type_changed={len(type_changed_fields)}")

    return f"{event_type} drift detected ({', '.join(parts)})."


def _requires_incident_response(event_type: str, severity: str) -> bool:
    """Critical severity or a breaking contract change warrants agent triage."""
    return severity == "critical" or event_type == "breaking"


def _trigger_agent_run(agent_run_id: int) -> None:
    """Fire-and-forget: kick off the LangGraph incident-triage agent
    (Phase 3) for a newly created AgentRun. Best-effort — if the `ai` extra
    isn't installed or the agent is disabled, drift detection still
    succeeds; this is purely additive, matching Phase 1's fail-open
    scheduler-registration pattern in routers/source_registry.py."""
    try:
        from services.ingestor.agent.runner import run_agent_for_observation

        asyncio.create_task(run_agent_for_observation(agent_run_id))
    except ImportError as exc:
        logger.warning(
            "agent_trigger_skipped",
            extra={"agent_run_id": agent_run_id, "error": str(exc)},
        )


async def create_contract_snapshot(
    db: AsyncSession,
    payload: ContractSnapshotCreate,
) -> tuple[ContractSnapshot | None, DriftEvent | None]:
    """Persist a contract snapshot and optional drift event.

    Returns:
        Tuple of (snapshot, drift_event). Returns (None, None) when source is missing.
    """
    source = await db.scalar(
        select(SourceProfile).where(
            SourceProfile.id == payload.source_id,
            SourceProfile.deleted_at.is_(None),
        )
    )
    if source is None:
        return None, None

    latest = await db.scalar(
        select(ContractSnapshot)
        .where(ContractSnapshot.source_id == payload.source_id)
        .order_by(ContractSnapshot.created_at.desc())
        .limit(1)
    )

    new_fingerprint = _fingerprint(payload.payload_schema)

    # Short-circuit: identical schema — persist the observation but skip diff.
    if latest is not None and latest.schema_fingerprint == new_fingerprint:
        snapshot = ContractSnapshot(
            source_id=payload.source_id,
            schema_version=payload.schema_version,
            payload_schema=payload.payload_schema,
            schema_fingerprint=new_fingerprint,
            compatibility_score=CONTRACT_COMPATIBILITY_MAX_SCORE,
            snapshot_note=payload.snapshot_note,
        )
        db.add(snapshot)
        await db.commit()
        await db.refresh(snapshot)
        return snapshot, None

    added_fields: list[str] = []
    removed_fields: list[str] = []
    type_changed_fields: dict[str, dict[str, str]] = {}

    if latest is not None:
        previous_flat = _flatten_schema(latest.payload_schema)
        current_flat = _flatten_schema(payload.payload_schema)
        added_fields, removed_fields, type_changed_fields = _diff_contract(
            previous_flat,
            current_flat,
        )

    score = _compatibility_score(added_fields, removed_fields, type_changed_fields)
    snapshot = ContractSnapshot(
        source_id=payload.source_id,
        schema_version=payload.schema_version,
        payload_schema=payload.payload_schema,
        schema_fingerprint=new_fingerprint,
        compatibility_score=score,
        snapshot_note=payload.snapshot_note,
    )
    db.add(snapshot)
    await db.flush()

    drift_event: DriftEvent | None = None
    agent_run: AgentRun | None = None
    incident_transitions: list[IncidentTransition] = []
    if latest is not None:
        event_type = _event_type(added_fields, removed_fields, type_changed_fields)
        if event_type != "none":
            severity = _severity(event_type, score)
            drift_event = DriftEvent(
                source_id=payload.source_id,
                previous_snapshot_id=latest.id,
                current_snapshot_id=snapshot.id,
                event_type=event_type,
                severity=severity,
                added_fields=added_fields,
                removed_fields=removed_fields,
                type_changed_fields=type_changed_fields,
                compatibility_score=score,
                summary=_summary(
                    event_type,
                    added_fields,
                    removed_fields,
                    type_changed_fields,
                ),
            )
            db.add(drift_event)

            if _requires_incident_response(event_type, severity):
                await db.flush()
                incident_transitions.append(
                    await open_or_update_incident(
                        db,
                        source=source,
                        trigger_type="drift",
                        severity=severity,
                        summary=drift_event.summary
                        or "Breaking contract drift detected.",
                        details={
                            "drift_event_id": drift_event.id,
                            "event_type": event_type,
                            "compatibility_score": score,
                            "removed_fields": removed_fields,
                            "type_changed_fields": type_changed_fields,
                        },
                    )
                )

            if _requires_incident_response(event_type, severity):
                await db.flush()  # assign drift_event.id for the incident payload
                incident = Observation(
                    source=source.name,
                    timestamp=_utcnow(),
                    raw_data={
                        "drift_event_id": drift_event.id,
                        "event_type": event_type,
                        "severity": severity,
                        "added_fields": added_fields,
                        "removed_fields": removed_fields,
                        "type_changed_fields": type_changed_fields,
                        "compatibility_score": score,
                        "summary": drift_event.summary,
                    },
                    tags=["incident", severity],
                    tenant_id=source.tenant_id,
                )
                db.add(incident)
                await db.flush()  # assign incident.id for the agent run FK
                agent_run = AgentRun(observation_id=incident.id, status="pending")
                db.add(agent_run)

    await db.commit()
    await db.refresh(snapshot)
    if drift_event is not None:
        await db.refresh(drift_event)
        await pubsub.publish_drift_event(
            source_id=payload.source_id,
            drift_event_id=drift_event.id,
            event_type=drift_event.event_type,
            severity=drift_event.severity,
            compatibility_score=drift_event.compatibility_score,
        )

    if agent_run is not None:
        _trigger_agent_run(agent_run.id)

    if incident_transitions:
        from services.ingestor.incident_lifecycle import (
            dispatch_incident_transitions,
        )

        await dispatch_incident_transitions(db, incident_transitions)

    return snapshot, drift_event


async def get_source_snapshots(
    db: AsyncSession,
    source_id: int,
    *,
    offset: int,
    limit: int,
) -> tuple[list[ContractSnapshot], int]:
    """List snapshots for one source with pagination."""
    base = select(ContractSnapshot).where(ContractSnapshot.source_id == source_id)
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                base.order_by(ContractSnapshot.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), total


async def get_source_drift_events(
    db: AsyncSession,
    source_id: int,
    *,
    offset: int,
    limit: int,
) -> tuple[list[DriftEvent], int]:
    """List drift events for one source with pagination."""
    base = select(DriftEvent).where(DriftEvent.source_id == source_id)
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                base.order_by(DriftEvent.created_at.desc()).offset(offset).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), total


async def get_compatibility_report(
    db: AsyncSession,
    source_id: int,
) -> CompatibilityReportResponse:
    """Compute compatibility report from the latest two snapshots."""
    snapshots = list(
        (
            await db.execute(
                select(ContractSnapshot)
                .where(ContractSnapshot.source_id == source_id)
                .order_by(ContractSnapshot.created_at.desc())
                .limit(2)
            )
        )
        .scalars()
        .all()
    )

    if not snapshots:
        return CompatibilityReportResponse(
            source_id=source_id,
            latest_snapshot_id=None,
            previous_snapshot_id=None,
            compatibility_score=CONTRACT_COMPATIBILITY_MAX_SCORE,
            drift_detected=False,
            event_type=None,
            severity=None,
            added_fields=[],
            removed_fields=[],
            type_changed_fields={},
        )

    latest = snapshots[0]
    if len(snapshots) == 1:
        return CompatibilityReportResponse(
            source_id=source_id,
            latest_snapshot_id=latest.id,
            previous_snapshot_id=None,
            compatibility_score=latest.compatibility_score,
            drift_detected=False,
            event_type=None,
            severity=None,
            added_fields=[],
            removed_fields=[],
            type_changed_fields={},
        )

    previous = snapshots[1]
    added_fields, removed_fields, type_changed_fields = _diff_contract(
        _flatten_schema(previous.payload_schema),
        _flatten_schema(latest.payload_schema),
    )
    event_type = _event_type(added_fields, removed_fields, type_changed_fields)

    return CompatibilityReportResponse(
        source_id=source_id,
        latest_snapshot_id=latest.id,
        previous_snapshot_id=previous.id,
        compatibility_score=latest.compatibility_score,
        drift_detected=event_type != "none",
        event_type=event_type if event_type != "none" else None,
        severity=_severity(event_type, latest.compatibility_score)
        if event_type != "none"
        else None,
        added_fields=added_fields,
        removed_fields=removed_fields,
        type_changed_fields=type_changed_fields,
    )
