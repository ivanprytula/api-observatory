"""Shared fixtures for services/mcp/tests.

No database, no testcontainers — this service holds no state of its own.
Required settings must be in os.environ *before* services.mcp.config is
first imported (module-level `Settings()` singleton), same reasoning as
tests/fixtures_shared.py does for the ingestor.
"""

from __future__ import annotations

import os


os.environ.setdefault("MCP_SERVICE_PASSWORD", "test-password")
os.environ.setdefault("INGESTOR_URL", "http://test-ingestor")

from collections.abc import AsyncGenerator  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
import respx  # noqa: E402

from services.mcp import auth_client, http  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_module_state() -> None:
    """Clear per-loop caches between tests so nothing leaks across them."""
    http._http_clients.clear()
    auth_client._token_states.clear()
    auth_client._login_locks.clear()


@pytest_asyncio.fixture()
async def mocked_ingestor() -> AsyncGenerator[respx.MockRouter]:
    """A respx router mocking the ingestor's base URL (respx patches at the
    httpx transport level, so any AsyncClient created while active — including
    the one services.mcp.http lazily creates — is intercepted)."""
    async with respx.mock(
        base_url="http://test-ingestor", assert_all_called=False
    ) as router:
        yield router
