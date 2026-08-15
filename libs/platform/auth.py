"""Internal service-to-service JWT authentication.

Provides token generation and verification for M2M calls within the cluster.
All services share a single INTERNAL_JWT_SECRET (from Secrets Manager).

Token claims:
- iss: "api-observatory"
- sub: <service-name>
- exp: now + 60 seconds (short-lived; refreshed on each outbound request)
- iat: issued-at timestamp

Usage — outbound request (service making the call):

    from libs.platform.auth import generate_internal_token
    import httpx

    headers = {"Authorization": f"Bearer {generate_internal_token('ingestor')}"}
    async with httpx.AsyncClient() as client:
        resp = await client.post("http://inference:8001/api/v1/embed", headers=headers)

Usage — inbound route (service receiving the call):

    from libs.platform.auth import InternalAuthDep

    @router.post("/admin/trigger-replay")
    async def trigger_replay(claims: InternalAuthDep) -> dict:
        ...

FastAPI dependency:

    type InternalAuthDep = Annotated[ServiceClaims, Depends(require_internal_auth)]
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel


logger = logging.getLogger(__name__)

_ISSUER = "api-observatory"
_TOKEN_TTL_SECONDS = 60
_ALGORITHM = "HS256"
_MIN_TOKEN_TTL_SECONDS = 30
_MAX_TOKEN_TTL_SECONDS = 300
_MTLS_ENABLED_ENV = "INTERNAL_MTLS_ENABLED"
_MTLS_ALLOWED_SUBJECTS_ENV = "INTERNAL_MTLS_ALLOWED_SUBJECTS"
_MTLS_VERIFY_HEADER = "X-Client-Cert-Verified"
_MTLS_SUBJECT_HEADER = "X-Client-Cert-Subject"
_PREVIOUS_SECRETS_ENV = "INTERNAL_JWT_SECRET_PREVIOUS"
_TTL_SECONDS_ENV = "INTERNAL_JWT_TTL_SECONDS"

type AuditEmitter = Callable[..., Awaitable[None]]
_security_audit_emitter: AuditEmitter | None = None


def set_security_audit_emitter(emitter: AuditEmitter | None) -> None:
    """Configure an optional async security-audit sink for auth events."""
    global _security_audit_emitter
    _security_audit_emitter = emitter


async def _emit_security_audit_event(**payload: Any) -> None:
    """Emit a security audit event when an emitter is configured.

    This keeps libs/platform independent from service-layer modules by using
    dependency injection instead of direct imports.
    """
    if _security_audit_emitter is None:
        return
    try:
        await _security_audit_emitter(**payload)
    except Exception as exc:
        logger.warning(
            "internal_auth_audit_emit_failed",
            extra={"event_type": payload.get("event_type"), "error": str(exc)},
        )


def _get_secret() -> str:
    """Read INTERNAL_JWT_SECRET from environment.

    Returns:
        Secret string for JWT signing/verification.

    Raises:
        RuntimeError: If INTERNAL_JWT_SECRET is not configured.
    """
    secret = os.environ.get("INTERNAL_JWT_SECRET")
    if not secret:
        raise RuntimeError(
            "INTERNAL_JWT_SECRET is not set. "
            "Configure it via environment variable or Secrets Manager."
        )
    return secret


def _verification_secrets() -> list[str]:
    """Return ordered secrets accepted for verification during key rotation."""
    secrets_ordered = [_get_secret()]
    previous_raw = os.environ.get(_PREVIOUS_SECRETS_ENV, "")
    if previous_raw:
        for secret in previous_raw.split(","):
            stripped = secret.strip()
            if stripped and stripped not in secrets_ordered:
                secrets_ordered.append(stripped)
    return secrets_ordered


def _token_ttl_seconds() -> int:
    """Return a bounded short-lived TTL for generated internal JWTs."""
    raw_value = os.environ.get(_TTL_SECONDS_ENV)
    if raw_value is None:
        return _TOKEN_TTL_SECONDS
    try:
        parsed = int(raw_value)
    except ValueError:
        logger.warning("internal_token_ttl_invalid", extra={"value": raw_value})
        return _TOKEN_TTL_SECONDS
    if parsed < _MIN_TOKEN_TTL_SECONDS:
        return _MIN_TOKEN_TTL_SECONDS
    if parsed > _MAX_TOKEN_TTL_SECONDS:
        return _MAX_TOKEN_TTL_SECONDS
    return parsed


class ServiceClaims(BaseModel):
    """Validated claims from an internal JWT token.

    Attributes:
        sub: Name of the calling service (e.g., "ingestor", "processor").
        iss: Must be "api-observatory".
        exp: Expiry timestamp (validated by PyJWT).
        iat: Issued-at timestamp.
    """

    sub: str
    iss: str
    exp: int
    iat: int
    mtls_subject: str | None = None


def _env_enabled(name: str) -> bool:
    """Return True when an environment flag is explicitly enabled."""
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _get_allowed_mtls_subjects() -> set[str]:
    """Return the configured client certificate subject allowlist."""
    raw_value = os.environ.get(_MTLS_ALLOWED_SUBJECTS_ENV, "")
    return {item.strip() for item in raw_value.split(",") if item.strip()}


def _require_mtls(
    client_cert_verified: str | None,
    client_cert_subject: str | None,
) -> str | None:
    """Validate mTLS proxy headers when internal mTLS is enabled.

    Returns the validated client certificate subject when mTLS is enabled,
    otherwise returns None.
    """
    if not _env_enabled(_MTLS_ENABLED_ENV):
        return None

    allowed_subjects = _get_allowed_mtls_subjects()
    if not allowed_subjects:
        logger.error("internal_mtls_misconfigured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal mTLS is enabled but no client certificate allowlist is configured",
        )

    if client_cert_verified != "SUCCESS":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Verified client certificate required for internal endpoint",
        )

    if not client_cert_subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing client certificate subject for internal endpoint",
        )

    if client_cert_subject not in allowed_subjects:
        logger.warning(
            "internal_mtls_subject_rejected",
            extra={"client_cert_subject": client_cert_subject},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client certificate subject is not authorized for internal endpoint",
        )

    return client_cert_subject


def generate_internal_token(service_name: str) -> str:
    """Generate a short-lived internal JWT for service-to-service calls.

    Args:
        service_name: Logical name of the calling service (e.g., "ingestor").

    Returns:
        Signed JWT string. Valid for _TOKEN_TTL_SECONDS seconds.

    Raises:
        RuntimeError: If INTERNAL_JWT_SECRET is not configured.
    """
    now = datetime.now(UTC)
    ttl_seconds = _token_ttl_seconds()
    payload: dict[str, Any] = {
        "iss": _ISSUER,
        "sub": service_name,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    token = jwt.encode(payload, _get_secret(), algorithm=_ALGORITHM)
    return token


def verify_internal_token(token: str) -> ServiceClaims:
    """Verify and decode an internal JWT.

    Args:
        token: Raw JWT string (without "Bearer " prefix).

    Returns:
        Decoded ServiceClaims.

    Raises:
        jwt.ExpiredSignatureError: If token has expired.
        jwt.InvalidTokenError: If token is invalid (wrong secret, issuer, algorithm).
    """
    payload: dict[str, Any] | None = None
    last_error: jwt.InvalidTokenError | None = None
    for secret in _verification_secrets():
        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=[_ALGORITHM],
                options={"require": ["iss", "sub", "exp", "iat"]},
            )
            break
        except jwt.ExpiredSignatureError:
            raise
        except jwt.InvalidTokenError as exc:
            last_error = exc
            continue

    if payload is None:
        if last_error is not None:
            raise last_error
        raise jwt.InvalidTokenError("Unable to verify internal token")

    if payload.get("iss") != _ISSUER:
        raise jwt.InvalidIssuerError(
            f"Invalid issuer: expected '{_ISSUER}', got '{payload.get('iss')}'"
        )

    return ServiceClaims(**payload)


async def require_internal_auth(
    authorization: Annotated[str | None, Header()] = None,
    client_cert_verified: Annotated[
        str | None, Header(alias=_MTLS_VERIFY_HEADER)
    ] = None,
    client_cert_subject: Annotated[
        str | None, Header(alias=_MTLS_SUBJECT_HEADER)
    ] = None,
) -> ServiceClaims:
    """FastAPI dependency: verify internal JWT from Authorization header.

    Args:
        authorization: Value of the Authorization header (injected by FastAPI).

    Returns:
        Validated ServiceClaims if token is valid.

    Raises:
        HTTPException 401: If header is missing, malformed, or token is invalid/expired.
    """
    if authorization is None:
        await _emit_security_audit_event(
            event_type="auth.internal",
            action="verify_token",
            decision="deny",
            actor_type="service",
            reason="missing_authorization_header",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header for internal endpoint",
        )

    if not authorization.startswith("Bearer "):
        await _emit_security_audit_event(
            event_type="auth.internal",
            action="verify_token",
            decision="deny",
            actor_type="service",
            reason="invalid_auth_scheme",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must use Bearer scheme",
        )

    raw_token = authorization.removeprefix("Bearer ")

    try:
        claims = verify_internal_token(raw_token)
    except jwt.ExpiredSignatureError:
        logger.warning("internal_token_expired")
        await _emit_security_audit_event(
            event_type="auth.internal",
            action="verify_token",
            decision="deny",
            actor_type="service",
            reason="token_expired",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Internal token has expired",
        ) from None
    except jwt.InvalidTokenError as exc:
        logger.warning("internal_token_invalid", extra={"error": str(exc)})
        await _emit_security_audit_event(
            event_type="auth.internal",
            action="verify_token",
            decision="deny",
            actor_type="service",
            reason="invalid_token",
            metadata_json={"error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal token",
        ) from exc

    try:
        mtls_subject = _require_mtls(client_cert_verified, client_cert_subject)
    except HTTPException as exc:
        await _emit_security_audit_event(
            event_type="auth.internal",
            action="mtls_check",
            decision="deny",
            actor_type="service",
            actor_id=claims.sub,
            reason=str(exc.detail),
            metadata_json={
                "client_cert_verified": client_cert_verified,
                "client_cert_subject": client_cert_subject,
            },
        )
        raise

    if mtls_subject is None:
        await _emit_security_audit_event(
            event_type="auth.internal",
            action="verify_token",
            decision="allow",
            actor_type="service",
            actor_id=claims.sub,
            metadata_json={"mtls_enabled": False},
        )
        return claims

    await _emit_security_audit_event(
        event_type="auth.internal",
        action="verify_token",
        decision="allow",
        actor_type="service",
        actor_id=claims.sub,
        metadata_json={"mtls_enabled": True, "mtls_subject": mtls_subject},
    )
    return claims.model_copy(update={"mtls_subject": mtls_subject})


# FastAPI Annotated type alias for use in route signatures.
type InternalAuthDep = Annotated[ServiceClaims, Depends(require_internal_auth)]
