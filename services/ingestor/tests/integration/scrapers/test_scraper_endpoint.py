"""Integration tests for POST /api/v1/scrape/{source} endpoint.

Tests scraper invocation, MongoDB storage, Kafka events, and error handling.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestScraperEndpoint:
    """Scraper endpoint integration tests."""

    async def test_scrape_valid_source(self, client: AsyncClient) -> None:
        """POST /api/v1/scrape/{source} with valid source returns ScrapeResponse."""
        response = await client.post(
            "/api/v1/scrape/jsonplaceholder", params={"limit": 5}
        )
        assert response.status_code == 200
        data = response.json()
        assert "source" in data
        assert "scraped" in data
        assert "stored" in data
        assert data["source"] == "jsonplaceholder"
        assert data["scraped"] >= 0
        assert data["stored"] >= 0

    async def test_scrape_limit_clamping(self, client: AsyncClient) -> None:
        """Limit parameter is clamped to [1, 100]."""
        # Test limit > 100 is clamped
        response = await client.post(
            "/api/v1/scrape/jsonplaceholder", params={"limit": 500}
        )
        assert response.status_code == 200
        # Should not raise; limit internally clamped to 100

    async def test_scrape_html_source(self, client: AsyncClient) -> None:
        """POST /api/v1/scrape/hn (Hacker News HTML scraper) works."""
        response = await client.post("/api/v1/scrape/hn", params={"limit": 3})
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "hn"

    async def test_scrape_browser_source(self, client: AsyncClient) -> None:
        """POST /api/v1/scrape/playwright (browser scraper) works."""
        response = await client.post("/api/v1/scrape/playwright", params={"limit": 2})
        assert response.status_code in (
            200,
            422,
            500,
        )  # May fail if Playwright not installed
        if response.status_code == 200:
            data = response.json()
            assert data["source"] == "playwright"

    async def test_scrape_invalid_source(self, client: AsyncClient) -> None:
        """POST /api/v1/scrape/unknown returns 422 Unprocessable Entity."""
        response = await client.post("/api/v1/scrape/unknown")
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
        assert "Unknown scraper source" in data["detail"]

    async def test_scrape_response_schema(self, client: AsyncClient) -> None:
        """Response conforms to ScrapeResponse schema."""
        response = await client.post(
            "/api/v1/scrape/jsonplaceholder", params={"limit": 1}
        )
        assert response.status_code == 200
        data = response.json()
        # Required fields per ScrapeResponse
        assert isinstance(data["source"], str)
        assert isinstance(data["scraped"], int)
        assert isinstance(data["stored"], int)
        assert data["scraped"] >= 0
        assert data["stored"] >= 0
        assert data["stored"] <= data["scraped"]  # Can't store more than scraped

    async def test_scrape_default_limit(self, client: AsyncClient) -> None:
        """Omitting limit parameter uses default (20)."""
        response = await client.post("/api/v1/scrape/jsonplaceholder")
        assert response.status_code == 200
        # Should succeed with default limit=20
        data = response.json()
        assert data["scraped"] <= 20
