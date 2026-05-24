"""Tests for aiohttp external API fetch with retry logic.

Step 7 Alternative: Real async HTTP with aiohttp (alternative to httpx).
Uses REST Countries API (restcountries.com) for country data fetching.
Demonstrates aiohttp-specific patterns: ClientSession lifecycle, TCPConnector pooling,
timeout configuration, and error handling.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from services.ingestor.fetch_aiohttp import (
    close_http_session,
    fetch_with_retry,
    get_http_session,
)


logger = logging.getLogger(__name__)

# --- Constants (DRY: avoid string duplication)
API_BASE = "https://restcountries.com/v3.1"
TEST_COUNTRY = "United States"
TEST_RESOURCE = f"name/{TEST_COUNTRY}"
MOCK_COUNTRY_RESPONSE = {
    "name": {"official": "United States of America", "common": "United States"},
    "capital": ["Washington, D.C."],
    "region": "Americas",
}
MOCK_COUNTRY_SUCCESS = {
    "name": {"official": "Germany", "common": "Germany"},
    "capital": ["Berlin"],
    "region": "Europe",
}

# Log messages
LOG_FETCH_EXHAUSTED = "fetch_exhausted"
LOG_FETCH_ATTEMPT = "fetch_attempt"
LOG_FETCH_SUCCESS = "fetch_success"
LOG_FETCH_TIMEOUT = "fetch_timeout"
LOG_FETCH_HTTP_ERROR = "fetch_http_error"
LOG_FETCH_RETRY = "fetch_retry"


@pytest.fixture
async def cleanup_http_session():
    """Fixture to ensure aiohttp session is cleaned up after each test."""
    yield
    await close_http_session()


@pytest.mark.integration
async def test_http_session_lifecycle(cleanup_http_session) -> None:
    """Verify aiohttp ClientSession is created once and reused, then can be closed."""
    # Get session twice - should be same instance
    session1 = await get_http_session()
    session2 = await get_http_session()
    assert session1 is session2

    # Close and verify new session is created
    await close_http_session()
    session3 = await get_http_session()
    assert session1 is not session3


@pytest.mark.integration
async def test_fetch_success_without_failures(cleanup_http_session) -> None:
    """Test successful fetch when simulate_failures=False."""

    async def mock_fetch(resource: str, simulate_failures: bool = False) -> dict:
        return MOCK_COUNTRY_RESPONSE

    with patch(
        "services.ingestor.fetch_aiohttp.fetch_from_external_api",
        side_effect=mock_fetch,
    ):
        result = await fetch_with_retry(TEST_RESOURCE, max_retries=3)
        assert result["name"]["common"] == "United States"


@pytest.mark.integration
async def test_fetch_retry_on_transient_failure(cleanup_http_session) -> None:
    """Retry succeeds after a transient failure."""
    call_count = 0

    async def mock_fetch(resource: str, simulate_failures: bool = False) -> dict:
        nonlocal call_count
        call_count += 1
        # Fail first time, succeed second
        if call_count < 2:
            raise TimeoutError("Timeout on call 1")
        return MOCK_COUNTRY_SUCCESS

    with patch(
        "services.ingestor.fetch_aiohttp.fetch_from_external_api",
        side_effect=mock_fetch,
    ):
        result = await fetch_with_retry(TEST_RESOURCE, max_retries=3)
        assert result["name"]["common"] == "Germany"
        assert call_count == 2


@pytest.mark.integration
async def test_fetch_retry_exhaustion(cleanup_http_session) -> None:
    """Max retries are respected and the last error is propagated."""
    call_count = 0

    async def always_fail(resource: str, simulate_failures: bool = False) -> dict:
        nonlocal call_count
        call_count += 1
        raise Exception("Persistent API error")

    with (
        patch(
            "services.ingestor.fetch_aiohttp.fetch_from_external_api",
            side_effect=always_fail,
        ),
        patch("services.ingestor.fetch_aiohttp.asyncio.sleep", new_callable=AsyncMock),
    ):
        with pytest.raises(Exception, match="Persistent API error"):
            await fetch_with_retry(TEST_RESOURCE, max_retries=3)
        assert call_count == 3


@pytest.mark.integration
async def test_fetch_timeout_error_handling(cleanup_http_session) -> None:
    """Timeout exceptions (aiohttp-style) are properly handled."""

    async def timeout_fetch(resource: str, simulate_failures: bool = False) -> dict:
        raise TimeoutError("Request timeout")

    with (
        patch(
            "services.ingestor.fetch_aiohttp.fetch_from_external_api",
            side_effect=timeout_fetch,
        ),
        patch("services.ingestor.fetch_aiohttp.asyncio.sleep", new_callable=AsyncMock),
    ):
        with pytest.raises(asyncio.TimeoutError):
            await fetch_with_retry(TEST_RESOURCE, max_retries=1)


@pytest.mark.integration
async def test_concurrent_fetches(cleanup_http_session) -> None:
    """Concurrent fetch requests work correctly with aiohttp."""

    async def mock_fetch(resource: str, simulate_failures: bool = False) -> dict:
        country_name = resource.split("/")[-1].replace("%20", " ")
        return {"name": {"common": country_name}, "region": "Test"}

    with patch(
        "services.ingestor.fetch_aiohttp.fetch_from_external_api",
        side_effect=mock_fetch,
    ):
        # Launch 5 concurrent fetches
        countries = ["France", "Spain", "Italy", "Greece", "Portugal"]
        tasks = [
            asyncio.create_task(fetch_with_retry(f"name/{country}", max_retries=3))
            for country in countries
        ]
        results = await asyncio.gather(*tasks)

        # All should succeed
        assert len(results) == 5
        assert all(r["name"]["common"] in countries for r in results)


@pytest.mark.integration
async def test_http_session_lifecycle_multiple_rounds(cleanup_http_session) -> None:
    """Test multiple cycles of get/close."""
    for _ in range(3):
        session = await get_http_session()
        assert session is not None
        await close_http_session()

    # Verify we can still get a session after cycles
    final_session = await get_http_session()
    assert final_session is not None


@pytest.mark.integration
async def test_aiohttp_connector_configuration(cleanup_http_session) -> None:
    """Verify aiohttp TCPConnector is properly configured."""
    session = await get_http_session()

    # Check that session has connector with expected pool limits
    assert session.connector is not None
    assert isinstance(session.connector, aiohttp.TCPConnector)

    # Verify timeout is set
    assert session.timeout is not None
    assert session.timeout.total == 30.0


@pytest.mark.integration
async def test_client_error_handling_aiohttp_style(cleanup_http_session) -> None:
    """aiohttp-specific ClientError is properly handled."""

    async def client_error_fetch(
        resource: str, simulate_failures: bool = False
    ) -> dict:
        raise aiohttp.ClientError("Network unreachable")

    with (
        patch(
            "services.ingestor.fetch_aiohttp.fetch_from_external_api",
            side_effect=client_error_fetch,
        ),
        patch("services.ingestor.fetch_aiohttp.asyncio.sleep", new_callable=AsyncMock),
    ):
        with pytest.raises(aiohttp.ClientError):
            await fetch_with_retry(TEST_RESOURCE, max_retries=2)
