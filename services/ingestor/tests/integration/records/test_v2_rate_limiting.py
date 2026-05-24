"""Integration tests for v2 rate-limiting routes (token bucket + sliding window).

Covers the happy path (201) and rate-limited path (429) for both strategies,
plus response header validation.
"""

from collections import defaultdict, deque

import pytest
import pytest_asyncio
from httpx import AsyncClient

from services.ingestor.constants import (
    SLIDING_WINDOW_LIMIT,
    TOKEN_BUCKET_CAPACITY,
)
from services.ingestor.routers import records_v2
from tests.shared.payloads import RECORD_API


_RECORD = RECORD_API
_TOKEN_BUCKET_URL = "/api/v2/records/token-bucket"
_SLIDING_WINDOW_URL = "/api/v2/records/sliding-window"


@pytest_asyncio.fixture(autouse=True)
async def _reset_v2_limiters() -> None:
    """Reset module-level rate limiter state before each test."""
    tb = records_v2._token_bucket
    tb._buckets = defaultdict(
        lambda: (float(tb.capacity), __import__("time").monotonic())
    )

    sw = records_v2._sliding_window
    sw._windows = defaultdict(deque)


# ---------------------------------------------------------------------------
# Token bucket — happy path
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_v2_token_bucket_create_record(client: AsyncClient) -> None:
    """POST to token-bucket endpoint creates a record (201)."""
    r = await client.post(_TOKEN_BUCKET_URL, json=_RECORD)

    assert r.status_code == 201
    body = r.json()
    assert body["source"] == _RECORD["source"]
    assert "id" in body


@pytest.mark.integration
async def test_v2_token_bucket_response_headers(client: AsyncClient) -> None:
    """Token-bucket response includes rate-limit headers."""
    r = await client.post(_TOKEN_BUCKET_URL, json=_RECORD)

    assert r.status_code == 201
    assert r.headers["X-RateLimit-Strategy"] == "token-bucket"
    assert r.headers["X-RateLimit-Limit"] == str(TOKEN_BUCKET_CAPACITY)
    assert "X-RateLimit-Remaining" in r.headers


@pytest.mark.integration
async def test_v2_token_bucket_rate_limited(client: AsyncClient) -> None:
    """Exhaust token bucket → 429 with Retry-After header."""
    # Drain the bucket (capacity = TOKEN_BUCKET_CAPACITY)
    for i in range(TOKEN_BUCKET_CAPACITY):
        r = await client.post(_TOKEN_BUCKET_URL, json=_RECORD)
        assert r.status_code == 201, f"Request {i + 1} failed unexpectedly"

    # Next request should be rate-limited
    r = await client.post(_TOKEN_BUCKET_URL, json=_RECORD)

    assert r.status_code == 429
    body = r.json()
    assert "detail" in body
    assert "token bucket" in body["detail"].lower()
    assert "Retry-After" in r.headers
    assert r.headers["X-RateLimit-Strategy"] == "token-bucket"


@pytest.mark.integration
async def test_v2_token_bucket_validation_422(client: AsyncClient) -> None:
    """Invalid payload → 422 (validation runs before rate limiting)."""
    r = await client.post(_TOKEN_BUCKET_URL, json={"source": "localhost"})

    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Sliding window — happy path
# ---------------------------------------------------------------------------
@pytest.mark.integration
async def test_v2_sliding_window_create_record(client: AsyncClient) -> None:
    """POST to sliding-window endpoint creates a record (201)."""
    r = await client.post(_SLIDING_WINDOW_URL, json=_RECORD)

    assert r.status_code == 201
    body = r.json()
    assert body["source"] == _RECORD["source"]
    assert "id" in body


@pytest.mark.integration
async def test_v2_sliding_window_response_headers(client: AsyncClient) -> None:
    """Sliding-window response includes rate-limit headers."""
    r = await client.post(_SLIDING_WINDOW_URL, json=_RECORD)

    assert r.status_code == 201
    assert r.headers["X-RateLimit-Strategy"] == "sliding-window"
    assert r.headers["X-RateLimit-Limit"] == str(SLIDING_WINDOW_LIMIT)
    assert "X-RateLimit-Remaining" in r.headers


@pytest.mark.integration
async def test_v2_sliding_window_rate_limited(client: AsyncClient) -> None:
    """Exhaust sliding window → 429 with Retry-After header."""
    # Fill the window (limit = SLIDING_WINDOW_LIMIT)
    for _ in range(SLIDING_WINDOW_LIMIT):
        r = await client.post(_SLIDING_WINDOW_URL, json=_RECORD)
        assert r.status_code == 201

    # Next request should be rate-limited
    r = await client.post(_SLIDING_WINDOW_URL, json=_RECORD)

    assert r.status_code == 429
    body = r.json()
    assert "detail" in body
    assert "sliding window" in body["detail"].lower()
    assert "Retry-After" in r.headers
    assert r.headers["X-RateLimit-Strategy"] == "sliding-window"


@pytest.mark.integration
async def test_v2_sliding_window_remaining_decrements(client: AsyncClient) -> None:
    """Remaining count decreases with each request."""
    r1 = await client.post(_SLIDING_WINDOW_URL, json=_RECORD)
    r2 = await client.post(_SLIDING_WINDOW_URL, json=_RECORD)

    remaining_1 = int(r1.headers["X-RateLimit-Remaining"])
    remaining_2 = int(r2.headers["X-RateLimit-Remaining"])

    assert remaining_1 > remaining_2
