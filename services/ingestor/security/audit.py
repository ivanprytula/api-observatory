"""Fail-open helper for emitting immutable security audit events."""

from __future__ import annotations

import logging

from services.ingestor.database import AsyncSessionLocal
from services.ingestor.repositories.security_audit import append_security_audit_event


logger = logging.getLogger(__name__)


async def emit_security_audit_event(
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
) -> None:
    """Write a security audit event to the append-only stream.

    The emitter is fail-open by design so authentication and authorization
    checks continue even if the audit sink is temporarily unavailable.
    """
    try:
        async with AsyncSessionLocal() as db:
            await append_security_audit_event(
                db,
                event_type=event_type,
                action=action,
                decision=decision,
                actor_type=actor_type,
                actor_id=actor_id,
                tenant_id=tenant_id,
                reason=reason,
                resource_type=resource_type,
                resource_id=resource_id,
                correlation_id=correlation_id,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata_json=metadata_json,
            )
    except Exception as exc:
        logger.warning(
            "security_audit_emit_failed",
            extra={"event_type": event_type, "error": str(exc)},
        )
