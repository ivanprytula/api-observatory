"""Authentication helpers — stateless JWT refresh tokens for MVP."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, status
from jwt.exceptions import DecodeError, ExpiredSignatureError, InvalidSignatureError

from libs.platform.auth import _emit_security_audit_event as emit_security_audit_event
from services.ingestor.config import settings
from services.ingestor.security.authorization import (
    AuthorizationInput,
    evaluate_authorization,
)


logger = logging.getLogger(__name__)

# Simple role names for RBAC learning examples.
DEFAULT_ROLE = "viewer"


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
# RBAC guards (unchanged)
# ============================================================================


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
    """Extract normalized roles from auth context."""
    roles = set()
    roles.update(_normalize_roles(claims_or_session.get("roles")))
    roles.update(_normalize_roles(claims_or_session.get("role")))
    if not roles and claims_or_session.get("scope") == "observations:write":
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
    """Create a session-based RBAC dependency."""
    normalized_required = {role.lower() for role in required_roles}

    async def _guard(
        session: dict[str, Any] = Depends(verify_session),
    ) -> dict[str, Any]:
        roles = _extract_roles(session)
        require_roles(normalized_required, roles)
        return session

    return _guard


def jwt_role_guard(*required_roles: str):
    """Create a JWT-based RBAC dependency."""
    normalized_required = {role.lower() for role in required_roles}

    async def _guard(
        claims: dict[str, Any] = Depends(verify_jwt_token),
    ) -> dict[str, Any]:
        roles = _extract_roles(claims)
        require_roles(normalized_required, roles)
        return claims

    return _guard
