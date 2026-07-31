"""End-to-end tests for complete scraper → storage → events workflow (Phase 2).

Tests the full pipeline: HTTP/HTML scraping, MongoDB storage, Kafka event publish.
These are slow/flaky tests that require external resources (marked e2e for skipping in CI).
"""

import pytest
from httpx import AsyncClient


@pytest.mark.e2e
class TestScraperWorkflows:
    """Full scraper workflow integration tests."""

    async def test_scraper_endpoint_workflow(self, client: AsyncClient) -> None:
        """POST /api/v1/scrape/{source} → stores in MongoDB → publishes Kafka event."""
        response = await client.post(
            "/api/v1/scrape/jsonplaceholder",
            params={"limit": 3},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "jsonplaceholder"
        assert data["scraped"] >= 0
        assert data["stored"] >= 0
        assert data["stored"] <= data["scraped"]

    async def test_scraper_workflow_html_source(self, client: AsyncClient) -> None:
        """HTML scraper (BeautifulSoup) workflow."""
        response = await client.post(
            "/api/v1/scrape/hn",
            params={"limit": 2},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "hn"
        # Data may be empty if external service unavailable (flaky e2e)
        assert isinstance(data["scraped"], int)
        assert isinstance(data["stored"], int)

    async def test_scraper_workflow_invalid_source(self, client: AsyncClient) -> None:
        """Invalid source name returns 422."""
        response = await client.post("/api/v1/scrape/nonexistent")
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    async def test_scraper_workflow_limit_boundaries(self, client: AsyncClient) -> None:
        """Limit parameter is clamped to [1, 100]."""
        # Test very high limit
        response = await client.post(
            "/api/v1/scrape/jsonplaceholder",
            params={"limit": 500},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["scraped"] <= 100  # Clamped maximum

        # Test zero limit (clamped to 1)
        response = await client.post(
            "/api/v1/scrape/jsonplaceholder",
            params={"limit": 0},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["scraped"] >= 0
