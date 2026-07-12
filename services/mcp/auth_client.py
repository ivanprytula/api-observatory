"""Token lifecycle for the `mcp-service` account against the ingestor's JWT auth.

Authenticates as a real registered user via the ingestor's actual
`POST /api/v1/auth/token` (OAuth2 password flow) — not in-process JWT minting —
so this server exercises the same auth surface any other API client does. See
`scripts/register_mcp_service_user.py` for the one-time account setup.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from services.mcp.config import settings
from services.mcp.http import get_http_client


@dataclass
class _TokenState:
    access_token: str
    refresh_token: str
    expires_at: float  # time.monotonic() deadline


_token_states: dict[asyncio.AbstractEventLoop, _TokenState] = {}
_login_locks: dict[asyncio.AbstractEventLoop, asyncio.Lock] = {}


def _get_login_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _login_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _login_locks[loop] = lock
    return lock


async def _login() -> _TokenState:
    """POST the real login endpoint and cache the resulting token state."""
    client = await get_http_client()
    response = await client.post(
        f"{settings.ingestor_url.rstrip('/')}/api/v1/auth/token",
        data={
            "username": settings.mcp_service_username,
            "password": settings.mcp_service_password,
        },
        timeout=settings.http_timeout_seconds,
    )
    response.raise_for_status()

    body = response.json()
    deadline = (
        time.monotonic()
        + (settings.jwt_expiry_minutes * 60)
        - settings.token_refresh_skew_seconds
    )
    state = _TokenState(
        access_token=body["access_token"],
        refresh_token=body["refresh_token"],
        expires_at=deadline,
    )
    _token_states[asyncio.get_running_loop()] = state
    return state


async def get_valid_token() -> str:
    """Return a valid access token, logging in (or re-logging in) as needed.

    A per-loop lock prevents concurrent tool calls that race past an expired
    token from firing N parallel logins — one waits, the rest reuse the token
    the winner obtained.
    """
    loop = asyncio.get_running_loop()
    state = _token_states.get(loop)
    if state is not None and time.monotonic() < state.expires_at:
        return state.access_token

    async with _get_login_lock():
        # Re-check: another caller may have already refreshed while we waited.
        state = _token_states.get(loop)
        if state is not None and time.monotonic() < state.expires_at:
            return state.access_token
        state = await _login()
        return state.access_token


async def force_relogin() -> str:
    """Discard any cached token and log in again — used after a 401."""
    loop = asyncio.get_running_loop()
    _token_states.pop(loop, None)
    async with _get_login_lock():
        state = await _login()
        return state.access_token
