"""E2E tests for external API fetch with retry & exponential backoff.

These tests validate the resilience patterns in app/fetch.py:
  - Successful fetch (no retries needed)
  - Graceful failure and retry logic with exponential backoff
  - Timeout handling
  - Exhaustion after max retries
  - Logging of attempts and delays

Dependencies:
  - jsonplaceholder.typicode.com (free, no auth required)
  - app/fetch.py (fetch_from_external_api, fetch_with_retry)

Run only E2E tests:
    uv run pytest tests/integration/records/test_e2e_fetch.py -v

Run all tests including E2E (normally skipped):
    uv run pytest -v -m e2e

Skip E2E tests (default):
    uv run pytest -v  # -m 'not e2e'
"""

from __future__ import annotations

import asyncio
import logging
import time
from unittest.mock import patch

import httpx
import pytest

from services.ingestor.fetch import (
    close_all_http_clients,
    close_http_client,
    fetch_from_external_api,
    fetch_with_retry,
    get_http_client,
)


logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
async def _cleanup_http_clients():
    """Fixture: Clean up HTTP clients after each test."""
    yield
    await close_all_http_clients()


class TestFetchFromExternalAPI:
    """Tests for basic fetch_from_external_api function."""

    @pytest.mark.e2e
    async def test_fetch_success_real_api(self) -> None:
        """Fetch real data from jsonplaceholder — no retries, should succeed."""
        # jsonplaceholder is a free API; /posts/1 always exists
        url = "https://jsonplaceholder.typicode.com/posts/1"
        result = await fetch_from_external_api(url, simulate_failures=False)

        assert isinstance(result, dict)
        assert "id" in result
        assert "userId" in result
        assert "title" in result
        assert result["id"] == 1

    @pytest.mark.e2e
    async def test_fetch_404_not_found(self) -> None:
        """Fetch non-existent resource — should raise HTTPStatusError."""
        url = "https://jsonplaceholder.typicode.com/posts/99999999"
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_from_external_api(url, simulate_failures=False)

    @pytest.mark.e2e
    async def test_fetch_invalid_url_connection_error(self) -> None:
        """Fetch invalid domain — should raise connection error."""
        url = "https://this-domain-does-not-exist-12345.example.invalid/api"
        with pytest.raises(httpx.ConnectError):
            await fetch_from_external_api(url, simulate_failures=False)

    @pytest.mark.e2e
    async def test_fetch_with_simulated_failures(self) -> None:
        """Simulated failures (10% rate) — use mock to force failure."""
        url = "https://jsonplaceholder.typicode.com/posts/1"

        # Patch random to always trigger the 10% failure case
        with patch("random.random", return_value=0.05):  # 0.05 < 0.1 → fails
            with pytest.raises(Exception, match="Simulated API failure"):
                await fetch_from_external_api(url, simulate_failures=True)


class TestFetchWithRetry:
    """Tests for fetch_with_retry function."""

    @pytest.mark.e2e
    async def test_retry_success_on_first_attempt(self) -> None:
        """Retry succeeds immediately (no retries needed)."""
        url = "https://jsonplaceholder.typicode.com/posts/1"
        result = await fetch_with_retry(url, max_retries=3, simulate_failures=False)

        assert isinstance(result, dict)
        assert result["id"] == 1

    @pytest.mark.e2e
    async def test_retry_success_after_simulated_failures(self) -> None:
        """Retry eventually succeeds after 2 simulated failures."""
        url = "https://jsonplaceholder.typicode.com/posts/1"
        attempt_count = [0]  # Mutable container to track calls

        # Simulate failures on 1st and 2nd attempts, succeed on 3rd
        original_fetch = fetch_from_external_api

        async def mock_fetch(url, simulate_failures=False):
            attempt_count[0] += 1
            if attempt_count[0] <= 2:
                raise Exception(f"Simulated failure #{attempt_count[0]}")
            return await original_fetch(url, simulate_failures=False)

        with (
            patch(
                "services.ingestor.fetch.fetch_from_external_api",
                side_effect=mock_fetch,
            ),
            patch("services.ingestor.fetch.logger.warning") as warning_mock,
        ):
            result = await fetch_with_retry(
                url,
                max_retries=4,
                simulate_failures=False,
            )

        assert isinstance(result, dict)
        assert result["id"] == 1
        assert attempt_count[0] == 3  # Tried 3 times

        # Verify retry warnings were emitted for simulated failures
        warning_messages = [call.args[0] for call in warning_mock.call_args_list]
        assert "fetch_retry" in warning_messages

    @pytest.mark.e2e
    async def test_retry_exhaustion_after_max_retries(self) -> None:
        """Retry exhausts all attempts and raises the final exception."""
        url = "https://example.invalid/api"  # Will always fail

        with pytest.raises(httpx.ConnectError):
            await fetch_with_retry(url, max_retries=3, simulate_failures=False)

    @pytest.mark.e2e
    async def test_retry_backoff_delays(self) -> None:
        """Verify exponential backoff delays: 1s, 2s, 4s, 8s (2^n pattern)."""
        attempt_times = []
        original_fetch = fetch_from_external_api

        async def mock_fetch_with_timing(url, simulate_failures=False):
            attempt_times.append(time.time())
            if len(attempt_times) < 4:
                raise Exception(f"Attempt {len(attempt_times)} failed")
            return await original_fetch(url, simulate_failures=False)

        with patch(
            "services.ingestor.fetch.fetch_from_external_api",
            side_effect=mock_fetch_with_timing,
        ):
            _ = await fetch_with_retry(
                "https://jsonplaceholder.typicode.com/posts/1",
                max_retries=5,
                simulate_failures=False,
            )

        # Should have 4 attempts
        assert len(attempt_times) == 4

        # Check delays between attempts
        delay_1_to_2 = attempt_times[1] - attempt_times[0]  # should be ~1s
        delay_2_to_3 = attempt_times[2] - attempt_times[1]  # should be ~2s
        delay_3_to_4 = attempt_times[3] - attempt_times[2]  # should be ~4s

        # Use 0.5s tolerance for timing variance
        assert 0.7 <= delay_1_to_2 <= 1.5, (
            f"Delay 1→2: {delay_1_to_2:.2f}s (expect ~1s)"
        )
        assert 1.7 <= delay_2_to_3 <= 2.5, (
            f"Delay 2→3: {delay_2_to_3:.2f}s (expect ~2s)"
        )
        assert 3.7 <= delay_3_to_4 <= 4.5, (
            f"Delay 3→4: {delay_3_to_4:.2f}s (expect ~4s)"
        )

    @pytest.mark.e2e
    async def test_retry_logging_attempt_numbers(self) -> None:
        """Verify logs show correct attempt numbers and retry messages."""
        url = "https://example.invalid/api"

        attempt_count = [0]

        async def mock_fetch(url, simulate_failures=False):
            attempt_count[0] += 1
            if attempt_count[0] < 2:
                raise Exception("First attempt fails")
            return await fetch_from_external_api(url, simulate_failures=False)

        with (
            patch(
                "services.ingestor.fetch.fetch_from_external_api",
                side_effect=mock_fetch,
            ),
            patch("services.ingestor.fetch.logger.info") as info_mock,
        ):
            with pytest.raises(httpx.ConnectError):
                await fetch_with_retry(
                    url,
                    max_retries=3,
                    simulate_failures=False,
                )

        # Check that attempt logging was emitted
        info_messages = [call.args[0] for call in info_mock.call_args_list]
        assert "fetch_attempt" in info_messages


class TestHttpClientLifecycle:
    """Tests for HTTP client creation and cleanup."""

    async def test_get_http_client_creates_client(self) -> None:
        """get_http_client creates a new AsyncClient on first call."""
        client = await get_http_client()

        assert isinstance(client, httpx.AsyncClient)
        assert client.is_closed is False

    async def test_get_http_client_reuses_same_client(self) -> None:
        """get_http_client returns the same client for the same event loop."""
        client1 = await get_http_client()
        client2 = await get_http_client()

        assert client1 is client2  # Same object

    async def test_close_http_client_closes_the_client(self) -> None:
        """close_http_client closes the client for the current loop."""
        client = await get_http_client()
        assert client.is_closed is False

        await close_http_client()

        # After close, the client should be closed
        assert client.is_closed is True

    async def test_close_http_client_is_idempotent(self) -> None:
        """close_http_client can be called multiple times safely."""
        await get_http_client()

        # First close
        await close_http_client()

        # Second close (should not raise)
        await close_http_client()

    async def test_close_all_http_clients_closes_all(self) -> None:
        """close_all_http_clients closes clients from all loops."""
        # Create first client in current loop
        client1 = await get_http_client()

        await close_all_http_clients()

        # After close_all, should be closed
        assert client1.is_closed is True


class TestRetryWithRealWorldScenarios:
    """Tests that simulate real-world scenarios."""

    @pytest.mark.e2e
    async def test_retry_handles_timeout_gracefully(self) -> None:
        """Verify timeout exceptions are caught and logged correctly."""
        timeout_exception = httpx.TimeoutException("Request timed out")

        async def mock_fetch(url, simulate_failures=False):
            raise timeout_exception

        with patch(
            "services.ingestor.fetch.fetch_from_external_api", side_effect=mock_fetch
        ):
            with pytest.raises(httpx.TimeoutException):
                await fetch_with_retry(
                    "https://example.invalid/slow-endpoint",
                    max_retries=2,
                    simulate_failures=False,
                )

    @pytest.mark.e2e
    async def test_concurrent_fetches_with_retry(self) -> None:
        """Multiple concurrent fetches should each get their own retry chain."""
        url = "https://jsonplaceholder.typicode.com/posts/1"

        # Run 5 concurrent fetches
        results = await asyncio.gather(
            fetch_with_retry(url, max_retries=2, simulate_failures=False),
            fetch_with_retry(url, max_retries=2, simulate_failures=False),
            fetch_with_retry(url, max_retries=2, simulate_failures=False),
            fetch_with_retry(url, max_retries=2, simulate_failures=False),
            fetch_with_retry(url, max_retries=2, simulate_failures=False),
        )

        # All should succeed
        assert len(results) == 5
        assert all(isinstance(r, dict) for r in results)
        assert all(r["id"] == 1 for r in results)
