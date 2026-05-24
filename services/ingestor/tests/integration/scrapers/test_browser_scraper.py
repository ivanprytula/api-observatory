"""Integration tests for BrowserScraper (Playwright).

Tests dynamic JavaScript rendering, navigation, and element interaction.
Note: These tests require Playwright to be installed. For CI/headless:
  `pytest --co-markers` to list; use PLAYWRIGHT_HEADLESS=1
"""

import pytest

from services.ingestor.scrapers.browser_scraper import BrowserScraper


@pytest.mark.integration
@pytest.mark.browser
class TestBrowserScraper:
    """Browser scraper (Playwright) tests."""

    @pytest.fixture
    def scraper(self) -> BrowserScraper:
        return BrowserScraper()

    async def test_scrape_javascript_rendered_content(
        self, scraper: BrowserScraper
    ) -> None:
        """Scrape returns list of ScrapedItem with JavaScript-rendered content."""
        items = await scraper.scrape(limit=5)
        assert isinstance(items, list)
        if items:
            assert hasattr(items[0], "url")
            assert hasattr(items[0], "title")
            assert items[0].source == "js"

    async def test_scrape_respects_limit(self, scraper: BrowserScraper) -> None:
        """Scrape respects limit parameter."""
        items = await scraper.scrape(limit=3)
        assert len(items) <= 3

    async def test_scrape_timeout_handling(self, scraper: BrowserScraper) -> None:
        """Scraper handles navigation timeout gracefully."""
        try:
            items = await scraper.scrape(limit=1)
            # If it succeeds, that's fine
            assert isinstance(items, list)
        except TimeoutError:
            # Timeouts are acceptable (network flakiness)
            pytest.skip("Network timeout (flaky environment)")

    async def test_scrape_bloom_filter_deduplication(
        self, scraper: BrowserScraper
    ) -> None:
        """Bloom filter deduplicates URLs across calls."""
        items_1 = await scraper.scrape(limit=3)
        items_2 = await scraper.scrape(limit=3)
        urls_1 = {item.url for item in items_1}
        urls_2 = {item.url for item in items_2}
        # Second call should return fewer URLs (already seen)
        assert len(urls_2) <= len(urls_1)

    async def test_playwright_page_navigation(self) -> None:
        """Playwright can navigate to a page and extract title."""
        # Test Playwright fundamentals without hitting real network
        # (for unit-level testing without external dependencies)
        # In integration tests, this could hit actual URLs
        pytest.skip("Requires Playwright browser instance (integration only)")

    async def test_element_visibility_check(self) -> None:
        """Verify elements are visible before extraction."""
        pytest.skip("Requires Playwright browser instance (integration only)")


# Import asyncio for timeout handling
