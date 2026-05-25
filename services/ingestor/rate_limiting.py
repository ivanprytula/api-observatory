"""Rate limiting configuration using slowapi."""

import jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from services.ingestor.config import settings


def get_user_or_ip_address(request: Request) -> str:
    """Extract a rate-limiting key based on authenticated user or IP address."""
    # 1. Try to extract user from JWT Bearer token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header[7:]
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            username = payload.get("sub")
            if username:
                return f"user:{username}"
        except Exception:
            pass  # nosec B110

    # 2. Try to extract session ID from cookie
    session_cookie = request.cookies.get("session")
    if session_cookie:
        return f"session:{session_cookie}"

    # 3. Fallback to client IP address
    return f"ip:{get_remote_address(request)}"


# Create a single limiter instance (imported everywhere needed)
# Uses Redis storage if enabled, otherwise defaults to in-memory
storage_uri = settings.redis_url if settings.redis_enabled else "memory://"
limiter = Limiter(key_func=get_user_or_ip_address, storage_uri=storage_uri)


__all__ = ["limiter"]
