"""Tenant-aware API key generation, hashing, and verification.

Design:
- Raw key format: ``dpak_<prefix8>.<secret56>`` (total ~68 chars, URL-safe)
  - ``dpak_`` prefix makes keys identifiable in logs / secret scanners
  - ``prefix8`` is the first 8 hex chars of a random 32-byte token → DB lookup index
  - ``secret56`` is the remaining 56 hex chars → never stored, only hashed
- DB stores ``key_prefix`` (8 chars) and ``key_hash`` (SHA-256 hex of the full secret56)
- Lookup: split on ``.``, query by prefix, then constant-time hash comparison
- ``require_scope(scope)`` returns a FastAPI dependency factory for scope enforcement
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestor.core.tenant import tenant_context
from services.ingestor.database import get_db
from services.ingestor.security.audit import emit_security_audit_event
from services.ingestor.security.authorization import (
    AuthorizationInput,
    evaluate_authorization,
)


logger = logging.getLogger(__name__)

# Prefix applied to every generated key so secret-scanners can detect leaks.
_KEY_PREFIX = "dpak_"
# Length of the prefix portion (hex chars) stored in DB for index lookup.
_PREFIX_LEN = 8


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns:
        (full_key, key_prefix, key_hash) where:
        - full_key is returned to the caller once and never stored.
        - key_prefix (8 hex chars) is stored for fast DB lookup.
        - key_hash (SHA-256 hex of the secret portion) is stored for verification.
    """
    raw = secrets.token_hex(32)  # 64 hex chars
    prefix = raw[:_PREFIX_LEN]
    secret = raw[_PREFIX_LEN:]
    full_key = f"{_KEY_PREFIX}{raw}"  # dpak_<64 hex chars>
    key_hash = _hash_secret(secret)
    return full_key, prefix, key_hash


def _hash_secret(secret: str) -> str:
    """Return SHA-256 hex digest of the secret portion of a key."""
    return hashlib.sha256(secret.encode()).hexdigest()


def _split_key(full_key: str) -> tuple[str, str] | None:
    """Split a submitted key into (prefix, secret).

    Returns None if the key is malformed.
    """
    if not full_key.startswith(_KEY_PREFIX):
        return None
    raw = full_key[len(_KEY_PREFIX) :]
    if len(raw) < _PREFIX_LEN + 1:
        return None
    prefix = raw[:_PREFIX_LEN]
    secret = raw[_PREFIX_LEN:]
    return prefix, secret


def verify_key_hash(submitted_key: str, stored_hash: str) -> bool:
    """Constant-time comparison of a submitted key against the stored hash.

    Args:
        submitted_key: The full raw key submitted by the caller.
        stored_hash: The SHA-256 hash stored in the database.

    Returns:
        True if the key matches the stored hash.
    """
    parts = _split_key(submitted_key)
    if parts is None:
        return False
    _, secret = parts
    computed = _hash_secret(secret)
    return hmac.compare_digest(computed, stored_hash)


# ---------------------------------------------------------------------------
# FastAPI dependency: verify_api_key
# ---------------------------------------------------------------------------


async def verify_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """FastAPI dependency that validates an ``X-API-Key`` header.

    Resolves the key against the database, checks expiry and active status,
    sets the tenant context, and returns the auth context dict::

        {
            "api_key_id": int,
            "tenant_id": int | None,
            "scopes": list[str],
            "name": str,
        }

    Raises:
        HTTPException 401: Missing or unrecognisable key.
        HTTPException 403: Key expired or revoked.
    """
    if not x_api_key:
        await emit_security_audit_event(
            event_type="auth.api_key",
            action="verify_key",
            decision="deny",
            actor_type="api_key",
            reason="missing_header",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    parts = _split_key(x_api_key)
    if parts is None:
        await emit_security_audit_event(
            event_type="auth.api_key",
            action="verify_key",
            decision="deny",
            actor_type="api_key",
            reason="malformed_key",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed API key",
        )
    prefix, _ = parts

    # Import here to avoid circular imports (models imports database).
    from services.ingestor.repositories.api_keys import get_api_key_by_prefix

    db_key = await get_api_key_by_prefix(db, prefix)
    if db_key is None or not verify_key_hash(x_api_key, db_key.key_hash):
        logger.warning("api_key_invalid", extra={"prefix": prefix})
        await emit_security_audit_event(
            event_type="auth.api_key",
            action="verify_key",
            decision="deny",
            actor_type="api_key",
            reason="invalid_key",
            metadata_json={"prefix": prefix},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    if not db_key.is_active:
        await emit_security_audit_event(
            event_type="auth.api_key",
            action="verify_key",
            decision="deny",
            actor_type="api_key",
            actor_id=str(db_key.id),
            tenant_id=db_key.tenant_id,
            reason="revoked_key",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key has been revoked",
        )

    now = datetime.now(UTC).replace(tzinfo=None)
    if db_key.expires_at is not None and db_key.expires_at < now:
        await emit_security_audit_event(
            event_type="auth.api_key",
            action="verify_key",
            decision="deny",
            actor_type="api_key",
            actor_id=str(db_key.id),
            tenant_id=db_key.tenant_id,
            reason="expired_key",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key has expired",
        )

    # Set tenant context for downstream CRUD / RLS.
    if db_key.tenant_id is not None:
        tenant_context.set(db_key.tenant_id)

    # Observation last-used timestamp asynchronously (fire-and-forget update).
    await _touch_last_used(db, db_key.id)

    logger.info(
        "api_key_authenticated",
        extra={"api_key_id": db_key.id, "tenant_id": db_key.tenant_id},
    )
    await emit_security_audit_event(
        event_type="auth.api_key",
        action="verify_key",
        decision="allow",
        actor_type="api_key",
        actor_id=str(db_key.id),
        tenant_id=db_key.tenant_id,
        metadata_json={"name": db_key.name, "scopes": db_key.scopes},
    )
    return {
        "api_key_id": db_key.id,
        "tenant_id": db_key.tenant_id,
        "scopes": db_key.scopes,
        "name": db_key.name,
    }


async def _touch_last_used(db: AsyncSession, api_key_id: int) -> None:
    """Update ``last_used_at`` on the ApiKey row."""
    from sqlalchemy import update

    from services.ingestor.models import ApiKey

    await db.execute(
        update(ApiKey)
        .where(ApiKey.id == api_key_id)
        .values(last_used_at=datetime.now(UTC).replace(tzinfo=None))
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Scope enforcement helper
# ---------------------------------------------------------------------------

#: All valid scope tokens recognised by this service.
VALID_SCOPES: frozenset[str] = frozenset(
    [
        "observations:read",
        "observations:write",
        "sources:read",
        "sources:write",
        "drift:read",
        "insights:read",
        "subscriptions:read",
        "subscriptions:write",
        "reporting:read",
        "etl:run",
        "abuse:read",
        "abuse:write",
        "admin",
    ]
)

# Type alias for the auth context returned by verify_api_key.
type ApiKeyContext = Annotated[dict[str, Any], Depends(verify_api_key)]


def require_scope(scope: str):
    """Return a FastAPI dependency that enforces the given scope.

    Usage::

        @router.get("/observations", dependencies=[Depends(require_scope("observations:read"))])
        async def list_observations(...): ...

    Or injected to get the context::

        @router.get("/observations")
        async def list_observations(
        ctx: Annotated[dict,
        Depends(require_scope("observations:read"))]): ...
    """

    async def _check(ctx: ApiKeyContext) -> dict[str, Any]:
        decision = evaluate_authorization(
            AuthorizationInput(
                action="api_key_scope_guard",
                principal_type="api_key",
                principal_id=ctx.get("api_key_id"),
                tenant_id=ctx.get("tenant_id"),
                scopes=set(ctx["scopes"]),
                required_scopes={scope},
            )
        )
        if not decision.allow:
            logger.warning(
                "api_key_scope_denied",
                extra={
                    "api_key_id": ctx.get("api_key_id"),
                    "required": scope,
                    "granted": ctx["scopes"],
                    "policy_name": decision.policy_name,
                    "policy_reason": decision.reason,
                },
            )
            await emit_security_audit_event(
                event_type="auth.api_key",
                action="scope_check",
                decision="deny",
                actor_type="api_key",
                actor_id=str(ctx.get("api_key_id"))
                if ctx.get("api_key_id") is not None
                else None,
                tenant_id=ctx.get("tenant_id"),
                reason=decision.reason,
                metadata_json={
                    "required_scope": scope,
                    "granted_scopes": ctx["scopes"],
                    "policy_name": decision.policy_name,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scope: {scope!r}",
            )
        await emit_security_audit_event(
            event_type="auth.api_key",
            action="scope_check",
            decision="allow",
            actor_type="api_key",
            actor_id=str(ctx.get("api_key_id"))
            if ctx.get("api_key_id") is not None
            else None,
            tenant_id=ctx.get("tenant_id"),
            metadata_json={"required_scope": scope},
        )
        return ctx

    return _check
