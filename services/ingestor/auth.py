"""Authentication helpers — stateless JWT refresh tokens for MVP."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Annotated, Any

import jwt
from casbin import Enforcer
from casbin.util import key_match
from casbin_sqlalchemy_adapter import Adapter as CasbinSQLAlchemyAdapter
from fastapi import Cookie, Depends, Header, HTTPException, status
from jwt.exceptions import DecodeError, ExpiredSignatureError, InvalidSignatureError

from libs.platform.auth import _emit_security_audit_event as emit_security_audit_event
from services.ingestor.config import settings


if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DEFAULT_ROLE = "user"

# Role tiers — update this dict when adding a new role. Unknown roles silently
# receive priority 0, which means they never win in resolve_effective_role's
# max() and are effectively invisible to API consumers.
_ROLE_PRIORITY: dict[str, int] = {"admin": 3, "manager": 2, "user": 1}


def resolve_effective_role(roles: set[str]) -> str:
    """Return the highest-priority role from an unordered Casbin role set.

    Roles absent from ``_ROLE_PRIORITY`` receive priority 0 (lower than any
    known tier), so they never surface as the effective role.
    """
    if not roles:
        return DEFAULT_ROLE
    return max(roles, key=lambda role: _ROLE_PRIORITY.get(role.lower(), 0))


def is_superuser(subject: str | None) -> bool:
    """True when the subject is the reserved global superadmin (root).

    The superadmin bypasses all Casbin enforcement via the model matcher, so it
    needs no g-rules and is tenant-agnostic. This single predicate is the source
    of truth used by three surfaces:
    - the Casbin matcher function (``is_superuser(r.sub)``),
    - ``casbin_guard`` (audit-logged short-circuit), and
    - ``TenantMiddleware`` (RLS bypass).
    """
    return bool(subject) and subject == settings.superadmin_subject


# ============================================================================
# JWT helpers
# ============================================================================


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


def decode_jwt_claims(token: str) -> dict[str, Any]:
    """Decode a JWT using the active rotation window without emitting audit events."""
    saw_invalid_signature = False
    for secret in _jwt_verification_secrets():
        try:
            return jwt.decode(token, secret, algorithms=[settings.jwt_algorithm])
        except InvalidSignatureError:
            saw_invalid_signature = True

    if saw_invalid_signature:
        raise InvalidSignatureError("Invalid token signature")
    raise DecodeError("Invalid token")


async def verify_jwt_token(
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """Verify JWT from Authorization header.

    Returns decoded token claims if valid.
    Usage: claims: dict = Depends(verify_jwt_token)
    """
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

    saw_invalid_signature = False
    for secret in _jwt_verification_secrets():
        try:
            payload = jwt.decode(
                credentials, secret, algorithms=[settings.jwt_algorithm]
            )

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
                metadata_json={"source": "http_header"},
            )
            return payload
        except ExpiredSignatureError:
            await emit_security_audit_event(
                event_type="auth.jwt",
                action="verify_token",
                decision="deny",
                actor_type="user",
                reason="token_expired",
                metadata_json={"source": "http_header"},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
            ) from None
        except InvalidSignatureError:
            saw_invalid_signature = True
            continue
        except DecodeError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token format",
            ) from None

    if saw_invalid_signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token signature",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid token",
    )


JwtDep = Annotated[dict[str, Any], Depends(verify_jwt_token)]


# ============================================================================
# Token creation
# ============================================================================


def create_jwt_token(
    sub: str,
    custom_claims: dict[str, Any] | None = None,
) -> str:
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


async def create_refresh_token(
    sub: str,
    custom_claims: dict[str, Any] | None = None,
) -> str:
    """Create a stateless refresh token JWT (MVP: no Redis revocation).

    Returns:
        Signed refresh token string.
    """
    now = datetime.now(UTC)
    jti = str(uuid.uuid4())
    expires_at = now + timedelta(days=settings.jwt_refresh_ttl_days)

    payload: dict[str, Any] = {
        "sub": sub,
        "iat": now,
        "exp": expires_at,
        "iss": settings.app_name,
        "jti": jti,
        "token_type": "refresh",
        "tenant_id": (custom_claims or {}).get("tenant_id"),
        **(custom_claims or {}),
    }

    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    logger.info("refresh_token_created", extra={"sub": sub, "jti": jti})
    return token


async def verify_refresh_token(token: str) -> dict[str, Any]:
    """Verify a stateless refresh token JWT (signature + expiry only).

    Raises HTTPException 401 if the token is invalid or expired.
    """
    saw_invalid_signature = False
    for secret in _jwt_verification_secrets():
        try:
            payload = jwt.decode(token, secret, algorithms=[settings.jwt_algorithm])
        except ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expired",
            ) from None
        except InvalidSignatureError:
            saw_invalid_signature = True
            continue
        except DecodeError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token format",
            ) from None

        if payload.get("token_type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not a refresh token",
            )

        return payload

    if saw_invalid_signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token signature",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
    )


async def revoke_refresh_token(jti: str) -> None:
    """Revoke refresh token (no-op for stateless MVP).

    In stateless mode, refresh tokens remain valid until natural expiry.
    """
    logger.info("refresh_token_revoke_skipped_stateless", extra={"jti": jti})


# ============================================================================
# Session helpers (stateless — no Redis)
# ============================================================================


async def create_session(
    user_id: str, custom_data: dict[str, Any] | None = None
) -> tuple[str, str]:
    """Create a stateless session ID.

    Returns (session_id, session_id).
    No persistence — suitable for MVP testing only.
    """
    session_id = str(uuid.uuid4())
    logger.info("session_created", extra={"user_id": user_id, "session_id": session_id})
    return session_id, session_id


async def delete_session(session_id: str) -> None:
    logger.info("session_deleted", extra={"session_id": session_id})


async def verify_session(
    session_id: str | None = Cookie(None),
) -> dict[str, Any]:
    """Verify session from cookie (stateless MVP — always returns minimal session)."""
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing session cookie",
        )
    return {"session_id": session_id}


# ============================================================================
# v1 Bearer token
# ============================================================================


async def verify_bearer_token(
    authorization: str | None = Header(None),
) -> str:
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


async def verify_jwt_token_str(token: str) -> dict[str, Any]:
    """Verify a JWT from a raw token string (for WebSocket use).

    Same decode logic as ``verify_jwt_token`` but accepts the raw string
    instead of an Authorization header — WebSocket handshakes pass the token
    via ``?token=`` query param since browsers cannot set WS headers.

    Raises HTTPException 401 on any validation failure.
    """
    saw_invalid_signature = False
    for secret in _jwt_verification_secrets():
        try:
            payload = jwt.decode(token, secret, algorithms=[settings.jwt_algorithm])

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
                metadata_json={"source": "websocket"},
            )
            return payload
        except ExpiredSignatureError:
            await emit_security_audit_event(
                event_type="auth.jwt",
                action="verify_token",
                decision="deny",
                actor_type="user",
                reason="token_expired",
                metadata_json={"source": "websocket"},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
            ) from None
        except InvalidSignatureError:
            saw_invalid_signature = True
            continue
        except DecodeError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token format",
            ) from None

    if saw_invalid_signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token signature",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid token",
    )


# ============================================================================
# Casbin RBAC
# ============================================================================


_casbin_enforcer: Enforcer | None = None


def _casbin_database_url() -> str:
    """Return a synchronous database URL for the casbin SQLAlchemy adapter."""
    url = settings.database_url
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "+psycopg")
    elif "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://")
    return url


def get_casbin_enforcer() -> Enforcer:
    """Lazily initialize and return the shared casbin Enforcer.

    Uses the SQLAlchemy adapter backed by the ``casbin_rule`` table.
    Falls back to a file adapter with default policies when the database
    is unavailable (e.g., in unit tests).
    The enforcer is cached on first call.
    """
    global _casbin_enforcer
    if _casbin_enforcer is None:
        model_path = os.path.join(
            os.path.dirname(__file__), "security", "casbin_model.conf"
        )
        policy_path = os.path.join(
            os.path.dirname(__file__), "security", "casbin_policy.csv"
        )
        try:
            adapter = CasbinSQLAlchemyAdapter(
                _casbin_database_url(), create_all_models=True
            )
            _casbin_enforcer = Enforcer(model_path, adapter)
        except Exception as exc:
            logger.warning(
                "casbin_fallback_to_file_adapter",
                extra={"error": str(exc), "policy_path": policy_path},
            )
            from casbin import FileAdapter

            _casbin_enforcer = Enforcer(model_path, FileAdapter(policy_path))
    _casbin_enforcer.add_named_domain_matching_func("g", key_match)
    _casbin_enforcer.add_function("is_superuser", is_superuser)
    return _casbin_enforcer


def casbin_guard(*required_roles: str):
    """Create a JWT-based Casbin RBAC dependency.

    Checks ``enforce()`` against persistent g-rules in the ``casbin_rule`` table.
    The JWT must carry ``sub`` and ``tenant_id`` claims.
    """
    normalized_required = [role.lower() for role in required_roles]

    async def _guard(
        claims: dict[str, Any] = Depends(verify_jwt_token),
    ) -> dict[str, Any]:
        sub = claims.get("sub") or ""
        if is_superuser(sub):
            await emit_security_audit_event(
                event_type="authz.sudo",
                action="authorize",
                decision="allow",
                actor_type="superadmin",
                actor_id=sub,
                tenant_id=claims.get("tenant_id"),
                metadata_json={"required_roles": list(normalized_required)},
            )
            return claims

        enforcer = get_casbin_enforcer()
        tenant_id = claims.get("tenant_id")
        domain = str(tenant_id) if tenant_id is not None else "*"

        for role in normalized_required:
            if enforcer.enforce(sub, domain, role, "access"):
                return claims

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient role permissions",
        )

    return _guard


def session_role_guard(*required_roles: str):
    """Create a session-based RBAC dependency for demo routes."""
    normalized_required = [role.lower() for role in required_roles]

    async def _guard(
        session: dict[str, Any] = Depends(verify_session),
    ) -> dict[str, Any]:
        raw_roles = session.get("roles", [])
        session_roles = (
            {str(role).lower() for role in raw_roles}
            if isinstance(raw_roles, list)
            else set()
        )
        role = session.get("role")
        if role:
            session_roles.add(str(role).lower())

        if not set(normalized_required).intersection(session_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role permissions",
            )
        return session

    return _guard


# ============================================================================
# Role management helpers
# ============================================================================


async def assign_user_role(
    session: AsyncSession,
    username: str,
    role: str,
    tenant_id: int | None = None,
) -> None:
    """Assign a Casbin g-rule mapping user -> role in domain."""
    from sqlalchemy import text

    enforcer = get_casbin_enforcer()
    domain = str(tenant_id) if tenant_id is not None else "*"
    enforcer.add_role_for_user_in_domain(username, role, domain)
    await session.execute(
        text(
            "INSERT INTO casbin_rule (ptype, v0, v1, v2) VALUES ('g', :v0, :v1, :v2) "
            "ON CONFLICT DO NOTHING"
        ),
        {"v0": username, "v1": role, "v2": domain},
    )
    await session.commit()


async def get_user_roles_in_domain(
    session: AsyncSession,
    username: str,
    tenant_id: int | None = None,
) -> set[str]:
    """Return Casbin roles for a user in a domain."""
    enforcer = get_casbin_enforcer()
    domain = str(tenant_id) if tenant_id is not None else "*"
    return set(enforcer.get_roles_for_user_in_domain(username, domain))


async def has_role_in_domain(
    session: AsyncSession,
    username: str,
    role: str,
    tenant_id: int | None = None,
) -> bool:
    """Check if user has a specific role in a domain."""
    roles = await get_user_roles_in_domain(session, username, tenant_id)
    return role.lower() in roles
