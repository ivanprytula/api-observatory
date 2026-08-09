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
    CONTRACT_BASELINE_CONFIRMATION_POLLS,
    CONTRACT_COMPATIBILITY_MAX_SCORE,
    CONTRACT_COMPATIBILITY_MIN_SCORE,
    CONTRACT_PENALTY_ADDED_FIELD,
    CONTRACT_PENALTY_REMOVED_FIELD,
    CONTRACT_PENALTY_TYPE_CHANGE,
)
from services.ingestor.models import (
    AgentRun,
    ContractBaseline,
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


# Lazy-loaded to avoid circular import during module initialization.
# Tests and callers can patch these names before create_contract_snapshot runs.
dispatch_incident_transitions = None
enqueue_incident_notification_requests = None


logger = logging.getLogger(__name__)

_ARRAY_INSPECTION_LIMIT = 20
_TYPE_UNION_SEPARATOR = "|"


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _merge_value_types(existing: str, observed: str) -> str:
    """Return a deterministic union of runtime types observed at one path."""
    types = set(existing.split(_TYPE_UNION_SEPARATOR))
    types.update(observed.split(_TYPE_UNION_SEPARATOR))
    return _TYPE_UNION_SEPARATOR.join(sorted(types))


def _merge_flat_schema(target: dict[str, str], observed: dict[str, str]) -> None:
    for path, value_type in observed.items():
        if existing := target.get(path):
            target[path] = _merge_value_types(existing, value_type)
        else:
            target[path] = value_type


def _flatten_value(value: Any, path: str) -> dict[str, str]:
    flat = {path: _value_type(value)}
    if isinstance(value, dict):
        for key, child in value.items():
            _merge_flat_schema(flat, _flatten_value(child, f"{path}.{key}"))
    elif isinstance(value, list):
        element_path = f"{path}[]"
        for element in value[:_ARRAY_INSPECTION_LIMIT]:
            _merge_flat_schema(flat, _flatten_value(element, element_path))
    return flat


def _flatten_schema(payload: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in payload.items():
        path = f"{prefix}.{key}" if prefix else key
        _merge_flat_schema(flat, _flatten_value(value, path))

    return flat


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _structure_fingerprint(flat_schema: dict[str, str]) -> str:
    """Return a value-independent fingerprint for one flattened structure."""
    canonical = json.dumps(flat_schema, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _diff_contract(
    previous_flat: dict[str, str],
    current_flat: dict[str, str],
) -> tuple[list[str], list[str], dict[str, dict[str, str]]]:
    added = sorted([k for k in current_flat if k not in previous_flat])
    removed = sorted(
        key
        for key in previous_flat
        if key not in current_flat
        and not _is_below_inconclusive_array(key, current_flat)
    )

    type_changed: dict[str, dict[str, str]] = {}
    shared = set(previous_flat).intersection(current_flat)
    for key in sorted(shared):
        if previous_flat[key] != current_flat[key]:
            type_changed[key] = {
                "from_type": previous_flat[key],
                "to_type": current_flat[key],
            }

    return added, removed, type_changed


def _is_below_inconclusive_array(path: str, flat_schema: dict[str, str]) -> bool:
    """Return whether ``path`` is below an observed array with no inspected children."""
    for array_path, value_type in flat_schema.items():
        if "array" not in value_type.split(_TYPE_UNION_SEPARATOR):
            continue
        element_prefix = f"{array_path}[]"
        has_inspected_children = any(
            candidate.startswith(element_prefix) for candidate in flat_schema
        )
        if not has_inspected_children and path.startswith(element_prefix):
            return True
    return False


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


async def get_active_contract_baseline(
    db: AsyncSession,
    source_id: int,
    *,
    for_update: bool = False,
) -> ContractBaseline | None:
    """Return the source's active accepted baseline."""
    statement = select(ContractBaseline).where(
        ContractBaseline.source_id == source_id,
        ContractBaseline.status == "active",
        ContractBaseline.deleted_at.is_(None),
    )
    if for_update:
        statement = statement.with_for_update()
    return await db.scalar(statement)


def _clear_candidate(baseline: ContractBaseline) -> None:
    baseline.candidate_snapshot_id = None
    baseline.candidate_schema_fingerprint = None
    baseline.candidate_observation_count = 0
    baseline.candidate_drift_event_id = None
    baseline.candidate_first_seen_at = None
    baseline.candidate_last_seen_at = None


async def accept_contract_baseline(
    db: AsyncSession,
    baseline: ContractBaseline,
    *,
    actor: str,
    acceptance_note: str | None,
    candidate_snapshot_id: int | None = None,
) -> ContractBaseline:
    """Promote the current candidate and retain the prior baseline as history."""
    selected_snapshot_id = candidate_snapshot_id or baseline.candidate_snapshot_id
    if selected_snapshot_id is None or baseline.candidate_snapshot_id is None:
        raise ValueError("No candidate contract is available for acceptance.")
    if selected_snapshot_id != baseline.candidate_snapshot_id:
        raise ValueError("The selected snapshot is not the current contract candidate.")

    candidate = await db.get(ContractSnapshot, selected_snapshot_id)
    if candidate is None or candidate.source_id != baseline.source_id:
        raise ValueError("The candidate snapshot is unavailable.")

    now = _utcnow()
    baseline.status = "superseded"
    baseline.active_key = None
    baseline.superseded_at = now
    await db.flush()

    promoted = ContractBaseline(
        source_id=baseline.source_id,
        tenant_id=baseline.tenant_id,
        baseline_snapshot_id=candidate.id,
        promoted_from_baseline_id=baseline.id,
        version=baseline.version + 1,
        status="active",
        active_key=f"source:{baseline.source_id}",
        accepted_by=actor,
        accepted_at=now,
        acceptance_note=acceptance_note,
    )
    db.add(promoted)
    await db.commit()
    await db.refresh(promoted)
    return promoted


async def create_contract_snapshot(
    db: AsyncSession,
    payload: ContractSnapshotCreate,
) -> tuple[ContractSnapshot | None, DriftEvent | None]:
    """Persist a contract snapshot and optional drift event.

    Returns:
        Tuple of (snapshot, drift_event). Returns (None, None) when source is missing.
    """
    source = await db.scalar(
        select(SourceProfile)
        .where(
            SourceProfile.id == payload.source_id,
            SourceProfile.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if source is None:
        return None, None

    global dispatch_incident_transitions, enqueue_incident_notification_requests
    if dispatch_incident_transitions is None:
        from services.ingestor.core.incident_notifications import (
            dispatch_incident_transitions as _dispatch_fn,
        )
        from services.ingestor.core.incident_notifications import (
            enqueue_incident_notification_requests as _enqueue_fn,
        )

        dispatch_incident_transitions = _dispatch_fn
        enqueue_incident_notification_requests = _enqueue_fn

    new_fingerprint = _fingerprint(payload.payload_schema)
    snapshot = ContractSnapshot(
        source_id=payload.source_id,
        schema_version=payload.schema_version,
        payload_schema=payload.payload_schema,
        schema_fingerprint=new_fingerprint,
        compatibility_score=CONTRACT_COMPATIBILITY_MAX_SCORE,
        snapshot_note=payload.snapshot_note,
    )
    db.add(snapshot)
    await db.flush()

    baseline = await get_active_contract_baseline(
        db,
        payload.source_id,
        for_update=True,
    )
    if baseline is None:
        baseline = ContractBaseline(
            source_id=payload.source_id,
            tenant_id=source.tenant_id,
            baseline_snapshot_id=snapshot.id,
            version=1,
            status="active",
            active_key=f"source:{payload.source_id}",
            accepted_by="system:first-observation",
            accepted_at=_utcnow(),
            acceptance_note="Initial observed contract baseline.",
        )
        db.add(baseline)
        await db.commit()
        await db.refresh(snapshot)
        return snapshot, None

    baseline_snapshot = await db.get(ContractSnapshot, baseline.baseline_snapshot_id)
    if baseline_snapshot is None:
        raise RuntimeError(
            f"Accepted baseline snapshot {baseline.baseline_snapshot_id} is missing."
        )

    baseline_flat = _flatten_schema(baseline_snapshot.payload_schema)
    current_flat = _flatten_schema(payload.payload_schema)
    added_fields, removed_fields, type_changed_fields = _diff_contract(
        baseline_flat,
        current_flat,
    )
    score = _compatibility_score(added_fields, removed_fields, type_changed_fields)
    snapshot.compatibility_score = score

    drift_event: DriftEvent | None = None
    agent_run: AgentRun | None = None
    incident_transitions: list[IncidentTransition] = []
    if not added_fields and not removed_fields and not type_changed_fields:
        _clear_candidate(baseline)
    else:
        candidate_fingerprint = _structure_fingerprint(current_flat)
        now = _utcnow()
        if baseline.candidate_schema_fingerprint == candidate_fingerprint:
            baseline.candidate_observation_count += 1
        else:
            baseline.candidate_schema_fingerprint = candidate_fingerprint
            baseline.candidate_observation_count = 1
            baseline.candidate_drift_event_id = None
            baseline.candidate_first_seen_at = now
        baseline.candidate_snapshot_id = snapshot.id
        baseline.candidate_last_seen_at = now

        candidate_confirmed = (
            baseline.candidate_observation_count >= CONTRACT_BASELINE_CONFIRMATION_POLLS
        )
        if candidate_confirmed and baseline.candidate_drift_event_id is None:
            event_type = _event_type(added_fields, removed_fields, type_changed_fields)
            severity = _severity(event_type, score)
            drift_event = DriftEvent(
                source_id=payload.source_id,
                previous_snapshot_id=baseline.baseline_snapshot_id,
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
            await db.flush()
            baseline.candidate_drift_event_id = drift_event.id

            if _requires_incident_response(event_type, severity):
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

    await enqueue_incident_notification_requests(db, incident_transitions)
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
    """Compare the latest observation with the active accepted baseline."""
    latest = await db.scalar(
        select(ContractSnapshot)
        .where(ContractSnapshot.source_id == source_id)
        .order_by(ContractSnapshot.created_at.desc())
        .limit(1)
    )

    if latest is None:
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

    baseline = await get_active_contract_baseline(db, source_id)
    if baseline is None:
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

    baseline_snapshot = await db.get(ContractSnapshot, baseline.baseline_snapshot_id)
    if baseline_snapshot is None:
        raise RuntimeError(
            f"Accepted baseline snapshot {baseline.baseline_snapshot_id} is missing."
        )

    added_fields, removed_fields, type_changed_fields = _diff_contract(
        _flatten_schema(baseline_snapshot.payload_schema),
        _flatten_schema(latest.payload_schema),
    )
    event_type = _event_type(added_fields, removed_fields, type_changed_fields)
    score = _compatibility_score(
        added_fields,
        removed_fields,
        type_changed_fields,
    )

    return CompatibilityReportResponse(
        source_id=source_id,
        latest_snapshot_id=latest.id,
        previous_snapshot_id=baseline_snapshot.id,
        compatibility_score=score,
        drift_detected=event_type != "none",
        event_type=event_type if event_type != "none" else None,
        severity=_severity(event_type, score) if event_type != "none" else None,
        added_fields=added_fields,
        removed_fields=removed_fields,
        type_changed_fields=type_changed_fields,
    )
