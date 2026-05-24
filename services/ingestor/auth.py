"""Authentication and authorization utilities.

Three auth patterns for learning:
1. Docs Auth (HTTP Basic Auth)
2. v1 API (Bearer Token + Cookie Session)
3. v2 API (JWT)
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from redis.asyncio import Redis

from services.ingestor.config import settings
from services.ingestor.security.audit import emit_security_audit_event
from services.ingestor.security.authorization import (
    AuthorizationInput,
    evaluate_authorization,
)


logger = logging.getLogger(__name__)

# HTTP Basic Auth scheme (for docs only)
security = HTTPBasic()

# Module-level type aliases (FastAPI-approved pattern)
type DocsCredentialsDep = Annotated[HTTPBasicCredentials, Depends(security)]

# Redis-backed session store (module-level singleton, initialized in lifespan).
# Key pattern: session:{session_id} → Redis hash {user_id, role, created_at}
_session_client: Redis | None = None

# Simple role names for RBAC learning examples.
DEFAULT_ROLE = "viewer"

_SESSION_KEY_PREFIX = "session:"


def _jwt_verification_secrets() -> list[str]:
    """Return ordered JWT verification secrets for rotation windows."""
    secrets_ordered = [settings.jwt_secret]
    previous_raw = settings.jwt_previous_secrets
    if previous_raw:
        for secret in previous_raw.split(","):
            stripped = secret.strip()
            if stripped and stripped not in secrets_ordered:
                secrets_ordered.append(stripped)
    return secrets_ordered


async def connect_session_store(redis_url: str) -> None:
    """Initialize the Redis session store.

    Args:
        redis_url: Redis DSN (e.g. redis://localhost:6379/0)
    """
    global _session_client
    _session_client = Redis.from_url(redis_url, decode_responses=True)
    await _session_client.ping()  # ty: ignore[invalid-await]
    logger.info("session_store_connected", extra={"url": redis_url})


async def disconnect_session_store() -> None:
    """Close the Redis session store connection."""
    global _session_client
    if _session_client is not None:
        await _session_client.aclose()
        _session_client = None
    logger.info("session_store_disconnected")


# ============================================================================
# Layer 1: Docs Auth (HTTP Basic Auth)
# ============================================================================


async def verify_docs_credentials(
    credentials: DocsCredentialsDep,
) -> HTTPBasicCredentials:
    """Verify credentials for documentation access."""
    if not settings.docs_username or not settings.docs_password:
        return credentials

    if credentials.username != settings.docs_username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    if credentials.password != settings.docs_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    return credentials


# ============================================================================
# Layer 2: v1 API Auth (Bearer Token + Sessions)
# ============================================================================


async def verify_bearer_token(
    authorization: str | None = Header(None),
) -> str:
    """Verify v1 bearer token from Authorization header.

    Usage: @router.post("/endpoint", dependencies=[Depends(verify_bearer_token)])
    or: api_key: str = Depends(verify_bearer_token)
    """
    if not settings.api_v1_bearer_token:
        return "public"  # Auth disabled

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme. Use: Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials != settings.api_v1_bearer_token:
        logger.warning("bearer_token_invalid", extra={"token_prefix": credentials[:10]})
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid bearer token",
        )

    return credentials


async def verify_session(
    session_id: str | None = Cookie(None),
) -> dict[str, Any]:
    """Verify session from cookie.

    Returns session data dict if valid, else raises 401.
    Usage: session: dict = Depends(verify_session)
    """
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing session cookie",
        )

    if _session_client is None:
        # Fallback: no Redis — reject all sessions (fail-closed, not fail-open)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session store unavailable",
        )

    key = f"{_SESSION_KEY_PREFIX}{session_id}"
    session_data: dict[str, Any] = await _session_client.hgetall(key)  # ty: ignore[invalid-await]
    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    # Set tenant context from session if present
    tenant_id = session_data.get("tenant_id")
    if tenant_id:
        from services.ingestor.core.tenant import tenant_context

        tenant_context.set(int(tenant_id))

    return session_data


def _normalize_roles(raw_roles: Any) -> set[str]:
    """Normalize role claims from str/list/tuple into a lowercase role set."""
    if raw_roles is None:
        return set()
    if isinstance(raw_roles, str):
        return {raw_roles.strip().lower()} if raw_roles.strip() else set()
    if isinstance(raw_roles, Iterable):
        roles = {str(role).strip().lower() for role in raw_roles if str(role).strip()}
        return roles
    return set()


def _extract_roles(claims_or_session: dict[str, Any]) -> set[str]:
    """Extract normalized roles from auth context.

    Supports `role` and `roles` fields for compatibility across session/JWT payloads.
    """
    roles = set()
    roles.update(_normalize_roles(claims_or_session.get("roles")))
    roles.update(_normalize_roles(claims_or_session.get("role")))
    if not roles and claims_or_session.get("scope") == "records:write":
        roles.add("writer")
    return roles


def require_roles(
    required_roles: set[str],
    current_roles: set[str],
    *,
    tenant_id: int | None = None,
    resource_tenant_id: int | None = None,
) -> None:
    """Raise 403 when the current role set does not satisfy policy checks."""
    decision = evaluate_authorization(
        AuthorizationInput(
            action="role_guard",
            principal_type="user",
            tenant_id=tenant_id,
            resource_tenant_id=resource_tenant_id,
            roles=current_roles,
            required_roles=required_roles,
        )
    )
    if not decision.allow:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient role permissions",
        )


def session_role_guard(*required_roles: str):
    """Create a session-based RBAC dependency.

    Example:
        AdminSessionDep = Annotated[dict[str, Any], Depends(session_role_guard("admin"))]
    """
    normalized_required = {role.lower() for role in required_roles}

    async def _guard(
        session: dict[str, Any] = Depends(verify_session),
    ) -> dict[str, Any]:
        roles = _extract_roles(session)
        require_roles(normalized_required, roles)
        return session

    return _guard


def jwt_role_guard(*required_roles: str):
    """Create a JWT-based RBAC dependency.

    Example:
        WriterJwtDep = Annotated[dict[str, Any], Depends(jwt_role_guard("writer", "admin"))]
    """
    normalized_required = {role.lower() for role in required_roles}

    async def _guard(
        claims: dict[str, Any] = Depends(verify_jwt_token),
    ) -> dict[str, Any]:
        roles = _extract_roles(claims)
        require_roles(normalized_required, roles)
        return claims

    return _guard


async def create_session(
    user_id: str, custom_data: dict[str, Any] | None = None
) -> tuple[str, str]:
    """Create a Redis-backed session. Returns (session_id, session_id).

    Key pattern: session:{session_id} → Redis hash with TTL.
    Falls back gracefully when Redis is unavailable (logs warning, returns ID).
    """
    import uuid

    session_id = str(uuid.uuid4())
    ttl_seconds = settings.token_expiry_hours * 3600

    fields: dict[str, str] = {
        "user_id": user_id,
        "role": (custom_data or {}).get("role", DEFAULT_ROLE),
        "tenant_id": str((custom_data or {}).get("tenant_id", "")),
        "created_at": datetime.now(UTC).isoformat(),
    }

    if _session_client is not None:
        key = f"{_SESSION_KEY_PREFIX}{session_id}"
        await _session_client.hset(key, mapping=fields)  # ty: ignore[invalid-await]
        await _session_client.expire(key, ttl_seconds)
    else:
        logger.warning(
            "session_store_unavailable",
            extra={"user_id": user_id, "fallback": "no_persistence"},
        )

    logger.info("session_created", extra={"user_id": user_id, "session_id": session_id})
    return session_id, session_id


async def delete_session(session_id: str) -> None:
    """Delete a session from Redis (logout / invalidation).

    Args:
        session_id: The session token to invalidate.
    """
    if _session_client is None:
        return
    key = f"{_SESSION_KEY_PREFIX}{session_id}"
    await _session_client.delete(key)
    logger.info("session_deleted", extra={"session_id": session_id})


# ============================================================================
# Layer 3: v2 API Auth (JWT)
# ============================================================================


def create_jwt_token(
    sub: str,
    custom_claims: dict[str, Any] | None = None,
) -> str:
    """Create JWT token.

    Args:
        sub: Subject (user ID or identifier)
        custom_claims: Additional claims to encode

    Returns:
        JWT token string

    Security note: In production, rotate secrets periodically.
    """
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.jwt_expiry_minutes)

    payload = {
        "sub": sub,
        "iat": now,
        "exp": expires_at,
        "iss": settings.app_name,
        "tenant_id": (custom_claims or {}).get("tenant_id"),
        **(custom_claims or {}),
    }

    token = jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    logger.info("jwt_token_created", extra={"sub": sub, "exp": expires_at.isoformat()})
    return token


async def verify_jwt_token(
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """Verify JWT from Authorization header.

    Returns decoded token claims if valid.
    Usage: claims: dict = Depends(verify_jwt_token)
    """
    if not authorization:
        await emit_security_audit_event(
            event_type="auth.jwt",
            action="verify_token",
            decision="deny",
            actor_type="user",
            reason="missing_authorization_header",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() != "bearer":
        await emit_security_audit_event(
            event_type="auth.jwt",
            action="verify_token",
            decision="deny",
            actor_type="user",
            reason="invalid_auth_scheme",
            metadata_json={"scheme": scheme},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme. Use: Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    saw_invalid_signature = False
    for secret in _jwt_verification_secrets():
        try:
            payload = jwt.decode(
                credentials,
                secret,
                algorithms=[settings.jwt_algorithm],
            )

            # Set tenant context from JWT claim if present
            tenant_id = payload.get("tenant_id")
            if tenant_id:
                from services.ingestor.core.tenant import tenant_context

                tenant_context.set(int(tenant_id))

            await emit_security_audit_event(
                event_type="auth.jwt",
                action="verify_token",
                decision="allow",
                actor_type="user",
                actor_id=str(payload.get("sub")) if payload.get("sub") else None,
                tenant_id=int(tenant_id) if tenant_id is not None else None,
                metadata_json={"issuer": payload.get("iss")},
            )

            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("jwt_expired")
            await emit_security_audit_event(
                event_type="auth.jwt",
                action="verify_token",
                decision="deny",
                actor_type="user",
                reason="token_expired",
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
            ) from None
        except jwt.InvalidSignatureError:
            saw_invalid_signature = True
            continue
        except jwt.DecodeError as e:
            logger.warning("jwt_decode_error", extra={"error": str(e)})
            await emit_security_audit_event(
                event_type="auth.jwt",
                action="verify_token",
                decision="deny",
                actor_type="user",
                reason="token_decode_error",
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token format",
            ) from None

    if saw_invalid_signature:
        logger.warning("jwt_invalid_signature")
        await emit_security_audit_event(
            event_type="auth.jwt",
            action="verify_token",
            decision="deny",
            actor_type="user",
            reason="invalid_signature",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token signature",
        ) from None

    await emit_security_audit_event(
        event_type="auth.jwt",
        action="verify_token",
        decision="deny",
        actor_type="user",
        reason="invalid_token",
    )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid token",
    )
