"""Shared fixtures for the services/ingestor/tests subtree.

The unit test slice needs a small subset of the broader test fixtures. Keeping
the required ones here avoids a hard dependency on the top-level ``tests``
package, which is not present in the CI-scoped unit job.
"""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from services.ingestor.config import Settings
from services.ingestor.database import get_db
from services.ingestor.main import app


@pytest.fixture()
def test_settings() -> Settings:
    """Override app settings for testing."""
    return Settings(
        environment="testing",
        app_version="1.0.0-test",
        docs_username=None,
        docs_password=None,
        api_v1_bearer_token=None,
        jwt_secret="test-secret-key-32-chars-minimum!!",
        db_echo=False,
    )


@pytest.fixture()
def settings_with_docs_auth() -> Settings:
    """Settings with documentation authentication enabled."""
    return Settings(
        environment="testing",
        docs_username="admin",
        docs_password="secret123",
        db_echo=False,
    )


@pytest.fixture()
def settings_with_api_token() -> Settings:
    """Settings with API v1 bearer token enabled."""
    return Settings(
        environment="testing",
        api_v1_bearer_token="test-bearer-token-123",
        db_echo=False,
    )


@pytest_asyncio.fixture()
async def client() -> AsyncGenerator[AsyncClient]:
    """Async HTTPX client with a lightweight DB override for unit tests."""

    async def _override() -> AsyncGenerator[object]:
        yield object()

    app.dependency_overrides[get_db] = _override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()
