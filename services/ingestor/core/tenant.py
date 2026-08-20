"""Tenant context and RLS middleware for multi-tenant isolation.

Uses ContextVar to track tenant_id and user_role per request, enabling Row-Level
Security (RLS) policies to filter data access in PostgreSQL.
"""

import logging
from contextvars import ContextVar

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send


logger = logging.getLogger(__name__)

# Context variables for the current request
tenant_context: ContextVar[int | None] = ContextVar("tenant_id", default=None)
role_context: ContextVar[str | None] = ContextVar("user_role", default=None)


def get_tenant_id() -> int | None:
    """Get the current request's tenant ID from context."""
    return tenant_context.get()


def get_user_role() -> str | None:
    """Get the current request's user role from context."""
    return role_context.get()


def resolve_tenant_from_jwt(token_str: str) -> tuple[int | None, str | None]:
    """Decode a JWT and return (tenant_id, user_role).

    This is the single place that maps a verified token to RBAC context.
    Returns (None, None) on any decode or auth error so the caller can
    fall back gracefully.
    """
    from services.ingestor.auth import (
        decode_jwt_claims,
        get_casbin_enforcer,
        is_superuser,
        resolve_effective_role,
    )

    payload = decode_jwt_claims(token_str)
    tenant_id = payload.get("tenant_id")
    sub = payload.get("sub")
    if tenant_id is not None and not isinstance(tenant_id, int):
        tenant_id = int(tenant_id)
    if is_superuser(sub):
        return tenant_id, "admin"
    if sub and tenant_id is not None:
        enforcer = get_casbin_enforcer()
        domain = str(tenant_id)
        casbin_roles = set(enforcer.get_roles_for_user_in_domain(sub, domain))
        return tenant_id, resolve_effective_role(casbin_roles) if casbin_roles else None
    if sub:
        return tenant_id, payload.get("role")
    return tenant_id, None


class TenantMiddleware:
    """Middleware that extracts tenant_id and user_role from request headers/tokens.

    Stores them in ContextVar so they're available throughout the request lifecycle
    (in CRUD functions, database queries, logging, etc.).

    Avoids BaseHTTPMiddleware to ensure reliable ContextVar propagation across
    async boundaries and event loop boundaries.

    Priority for tenant_id extraction:
    1. Authorization: Bearer JWT (verified tenant claim)
    2. X-Tenant-ID header for unauthenticated local/demo routes only
    3. None (no tenant context, public/global scope)
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Extract and store tenant context for the request."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        tenant_id: int | None = None
        user_role: str | None = None

        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token_str = auth_header[7:].strip()
            try:
                tenant_id, user_role = resolve_tenant_from_jwt(token_str)
            except Exception as exc:
                logger.debug(
                    "jwt_tenant_context_unavailable", extra={"error": str(exc)}
                )
        else:
            tenant_id_raw = request.headers.get("X-Tenant-ID")
            if tenant_id_raw:
                try:
                    tenant_id = int(tenant_id_raw)
                except (TypeError, ValueError):
                    logger.warning(
                        "invalid_tenant_header", extra={"value": tenant_id_raw}
                    )

        # Store in context variables for the request
        t_token = tenant_context.set(tenant_id)
        r_token = role_context.set(user_role)
        try:
            await self.app(scope, receive, send)
        finally:
            # Always reset context to clean up (prevents context leaks across requests)
            tenant_context.reset(t_token)
            role_context.reset(r_token)
