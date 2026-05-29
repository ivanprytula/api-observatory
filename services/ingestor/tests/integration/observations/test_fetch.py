"""Tests for external API fetch with retry logic and httpx.

Step 7: Real async HTTP with httpx, retry logic, and error handling.
Demonstrates resilience patterns: graceful failure, exponential backoff, timeouts.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from services.ingestor.fetch import (
    close_http_client,
    fetch_with_retry,
    get_http_client,
)


logger = logging.getLogger(__name__)

# --- Constants (DRY: avoid string duplication)
API_BASE = "https://jsonplaceholder.typicode.com"
TEST_POST_ID = 1
TEST_POST_URL = f"{API_BASE}/posts/{TEST_POST_ID}"
MOCK_POST_RESPONSE = {"id": TEST_POST_ID, "title": "Test Post", "data": "success"}
MOCK_POST_SUCCESS = {"id": TEST_POST_ID, "title": "Success after retry"}

# Log messages
LOG_FETCH_EXHAUSTED = "fetch_exhausted"
LOG_FETCH_ATTEMPT = "fetch_attempt"
LOG_FETCH_SUCCESS = "fetch_success"
LOG_FETCH_TIMEOUT = "fetch_timeout"
LOG_FETCH_HTTP_ERROR = "fetch_http_error"
LOG_FETCH_RETRY = "fetch_retry"


@pytest.fixture
async def cleanup_http_client():
    """Fixture to ensure HTTP client is cleaned up after each test."""
    yield
    await close_http_client()


@pytest.mark.integration
async def test_http_client_lifecycle(cleanup_http_client) -> None:
    """Verify HTTP client is created once and reused, then can be closed."""
    # Get client twice - should be same instance
    client1 = await get_http_client()
    client2 = await get_http_client()
    assert client1 is client2

    # Close and verify new client is created
    await close_http_client()
    client3 = await get_http_client()
    assert client1 is not client3


@pytest.mark.integration
async def test_fetch_success_without_failures(cleanup_http_client) -> None:
    """Test successful fetch when simulate_failures=False."""

    async def mock_fetch(url: str, simulate_failures: bool = False) -> dict:
        return MOCK_POST_RESPONSE

    with patch(
        "services.ingestor.fetch.fetch_from_external_api", side_effect=mock_fetch
    ):
        result = await fetch_with_retry(TEST_POST_URL, max_retries=3)
        assert result["title"] == "Test Post"


@pytest.mark.integration
async def test_fetch_retry_on_transient_failure(cleanup_http_client) -> None:
    """Retry succeeds after a transient failure."""
    call_count = 0

    async def mock_fetch(url: str, simulate_failures: bool = False) -> dict:
        nonlocal call_count
        call_count += 1
        # Fail first time, succeed second
        if call_count < 2:
            raise httpx.TimeoutException("Timeout on call 1")
        return MOCK_POST_SUCCESS

    with patch(
        "services.ingestor.fetch.fetch_from_external_api", side_effect=mock_fetch
    ):
        result = await fetch_with_retry(TEST_POST_URL, max_retries=3)
        assert result["title"] == "Success after retry"
        assert call_count == 2


@pytest.mark.integration
async def test_fetch_retry_exhaustion(cleanup_http_client) -> None:
    """Max retries are respected and the last error is propagated."""
    call_count = 0

    async def always_fail(url: str, simulate_failures: bool = False) -> dict:
        nonlocal call_count
        call_count += 1
        raise Exception("Persistent API error")

    with (
        patch(
            "services.ingestor.fetch.fetch_from_external_api", side_effect=always_fail
        ),
        patch("services.ingestor.fetch.asyncio.sleep", new_callable=AsyncMock),
    ):
        with pytest.raises(Exception, match="Persistent API error"):
            await fetch_with_retry(TEST_POST_URL, max_retries=3)
        assert call_count == 3


@pytest.mark.integration
async def test_fetch_timeout_error_handling(cleanup_http_client) -> None:
    """Timeout exceptions are properly handled."""

    async def timeout_fetch(url: str, simulate_failures: bool = False) -> dict:
        raise httpx.TimeoutException("Request timeout")

    with (
        patch(
            "services.ingestor.fetch.fetch_from_external_api", side_effect=timeout_fetch
        ),
        patch("services.ingestor.fetch.asyncio.sleep", new_callable=AsyncMock),
    ):
        with pytest.raises(httpx.TimeoutException):
            await fetch_with_retry(TEST_POST_URL, max_retries=1)


@pytest.mark.integration
async def test_concurrent_fetches(cleanup_http_client) -> None:
    """Concurrent fetch requests work correctly."""

    async def mock_fetch(url: str, simulate_failures: bool = False) -> dict:
        post_id = int(url.split("/")[-1])
        return {"id": post_id, "title": f"Post {post_id}"}

    with patch(
        "services.ingestor.fetch.fetch_from_external_api", side_effect=mock_fetch
    ):
        # Launch 5 concurrent fetches
        tasks = [
            fetch_with_retry(f"{API_BASE}/posts/{i}", max_retries=3)
            for i in range(1, 6)
        ]
        results = await asyncio.gather(*tasks)

        # All should succeed
        assert len(results) == 5
        assert all(r["title"].startswith("Post") for r in results)


@pytest.mark.integration
async def test_http_client_lifecycle_multiple_rounds(cleanup_http_client) -> None:
    """Test multiple cycles of get/close."""
    for _ in range(3):
        client = await get_http_client()
        assert client is not None
        await close_http_client()

    # Verify we can still get a client after cycles
    final_client = await get_http_client()
    assert final_client is not None
