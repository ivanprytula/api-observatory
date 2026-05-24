"""Integration tests for HtmlScraper (BeautifulSoup HTML parsing).

Tests CSS selector extraction, malformed HTML handling, and Hacker News scraping.
"""

import pytest
from bs4 import BeautifulSoup

from services.ingestor.scrapers.html_scraper import HtmlScraper


@pytest.mark.integration
class TestHtmlScraper:
    """HTML scraper (BeautifulSoup) tests."""

    @pytest.fixture
    def scraper(self) -> HtmlScraper:
        return HtmlScraper()

    async def test_scrape_success(self, scraper: HtmlScraper) -> None:
        """Successful scrape returns list of ScrapedItem."""
        items = await scraper.scrape(limit=5)
        assert isinstance(items, list)
        assert len(items) <= 5
        if items:
            assert hasattr(items[0], "url")
            assert hasattr(items[0], "title")
            assert items[0].source == "hn"

    async def test_scrape_respects_limit(self, scraper: HtmlScraper) -> None:
        """Scrape respects limit parameter."""
        items = await scraper.scrape(limit=3)
        assert len(items) <= 3

    async def test_scrape_bloom_filter_deduplication(
        self, scraper: HtmlScraper
    ) -> None:
        """Bloom filter deduplicates URLs across calls."""
        items_1 = await scraper.scrape(limit=5)
        items_2 = await scraper.scrape(limit=5)
        urls_1 = {item.url for item in items_1}
        urls_2 = {item.url for item in items_2}
        # Second call should return new URLs or empty (already seen)
        assert len(urls_2) < len(urls_1) or len(urls_2) == 0

    async def test_html_parsing_valid(self) -> None:
        """BeautifulSoup parses valid HTML correctly."""
        html = "<html><body><a href='http://example.com'>Example</a></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        link = soup.find("a")
        assert link is not None
        assert link.text == "Example"

    async def test_html_parsing_malformed(self) -> None:
        """BeautifulSoup handles malformed HTML gracefully."""
        html = "<html><body><a href='http://example.com'>Unclosed"
        soup = BeautifulSoup(html, "html.parser")
        # BeautifulSoup doesn't raise on malformed HTML, it recovers
        assert soup is not None

    async def test_css_selector_extraction(self) -> None:
        """CSS selectors extract elements correctly."""
        html = "<tr class='athing'><span class='titleline'><a href='story'>Title</a></span></tr>"
        soup = BeautifulSoup(html, "html.parser")
        row = soup.select_one("tr.athing")
        assert row is not None
        title_link = row.select_one("span.titleline > a")
        assert title_link is not None
        assert title_link.text == "Title"

    async def test_nonexistent_selector(self) -> None:
        """Nonexistent CSS selector returns None, not error."""
        html = "<html><body></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        result = soup.select_one("tr.athing")
        assert result is None
