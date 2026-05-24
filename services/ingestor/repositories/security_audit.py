"""Append-only persistence for security audit events."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.models import SecurityAuditEvent, _utcnow


def _canonical_json(payload: dict) -> str:
    """Serialize metadata in a stable form for deterministic event hashing."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _compute_event_hash(
    *,
    prev_event_hash: str | None,
    created_at: datetime,
    event_type: str,
    action: str,
    decision: str,
    actor_type: str,
    actor_id: str | None,
    tenant_id: int | None,
    resource_type: str | None,
    resource_id: str | None,
    metadata_json: dict,
) -> str:
    """Compute a tamper-evident hash over event content and predecessor hash."""
    message = "|".join(
        [
            prev_event_hash or "",
            created_at.isoformat(),
            event_type,
            action,
            decision,
            actor_type,
            actor_id or "",
            str(tenant_id) if tenant_id is not None else "",
            resource_type or "",
            resource_id or "",
            _canonical_json(metadata_json),
        ]
    )
    return hashlib.sha256(message.encode("utf-8")).hexdigest()


async def append_security_audit_event(
    db: AsyncSession,
    *,
    event_type: str,
    action: str,
    decision: str,
    actor_type: str,
    actor_id: str | None = None,
    tenant_id: int | None = None,
    reason: str | None = None,
    resource_type: str | None = None,
    resource_id: str | int | None = None,
    correlation_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata_json: dict | None = None,
) -> SecurityAuditEvent:
    """Insert a security audit event and return the persisted row."""
    metadata = metadata_json or {}

    previous_result = await db.execute(
        select(SecurityAuditEvent.event_hash)
        .order_by(SecurityAuditEvent.id.desc())
        .limit(1)
    )
    prev_event_hash = previous_result.scalar_one_or_none()

    created_at = _utcnow()
    event_hash = _compute_event_hash(
        prev_event_hash=prev_event_hash,
        created_at=created_at,
        event_type=event_type,
        action=action,
        decision=decision,
        actor_type=actor_type,
        actor_id=actor_id,
        tenant_id=tenant_id,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        metadata_json=metadata,
    )

    row = SecurityAuditEvent(
        event_type=event_type,
        action=action,
        decision=decision,
        reason=reason,
        actor_type=actor_type,
        actor_id=actor_id,
        tenant_id=tenant_id,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        correlation_id=correlation_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata_json=metadata,
        prev_event_hash=prev_event_hash,
        event_hash=event_hash,
        created_at=created_at,
    )

    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row
