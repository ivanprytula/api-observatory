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


class TenantMiddleware:
    """Middleware that extracts tenant_id and user_role from request headers/tokens.

    Stores them in ContextVar so they're available throughout the request lifecycle
    (in CRUD functions, database queries, logging, etc.).

    Avoids BaseHTTPMiddleware to ensure reliable ContextVar propagation across
    async boundaries and event loop boundaries.

    Priority for tenant_id extraction:
    1. X-Tenant-ID header (direct numeric ID)
    2. Authorization: Bearer JWT (decode to extract tenant_id claim)
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

        # 1. Try X-Tenant-ID header first
        tenant_id_raw = request.headers.get("X-Tenant-ID")
        if tenant_id_raw:
            try:
                tenant_id = int(tenant_id_raw)
            except ValueError, TypeError:
                logger.warning(f"Invalid X-Tenant-ID header: {tenant_id_raw!r}")

        # 2. If no X-Tenant-ID, try to extract from JWT Bearer token
        if not tenant_id:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.lower().startswith("bearer "):
                token_str = auth_header[7:].strip()
                try:
                    import jwt

                    from services.ingestor.config import settings

                    # Decode JWT to extract tenant_id and role claims
                    # Verification ensures token is authentic (not tampered)
                    payload = jwt.decode(
                        token_str,
                        settings.jwt_secret,
                        algorithms=[settings.jwt_algorithm],
                    )
                    tenant_id = payload.get("tenant_id")
                    user_role = payload.get("role")
                    if tenant_id is not None and not isinstance(tenant_id, int):
                        tenant_id = int(tenant_id)
                except (jwt.InvalidTokenError, jwt.DecodeError, ValueError) as e:
                    # Log at debug level — auth errors are expected during normal operation
                    logger.debug(f"Failed to decode JWT bearer token: {e}")
                except Exception as e:
                    # Catch unexpected errors (import failures, etc.)
                    logger.debug(f"Unexpected error extracting tenant from JWT: {e}")

        # Store in context variables for the request
        t_token = tenant_context.set(tenant_id)
        r_token = role_context.set(user_role)
        try:
            await self.app(scope, receive, send)
        finally:
            # Always reset context to clean up (prevents context leaks across requests)
            tenant_context.reset(t_token)
            role_context.reset(r_token)
