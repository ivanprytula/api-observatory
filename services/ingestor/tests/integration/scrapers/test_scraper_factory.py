"""Integration tests for ScraperFactory.

Tests factory registration, scraper instantiation, and error handling.
"""

import pytest

from services.ingestor.scrapers import Scraper, ScraperFactory


@pytest.mark.integration
class TestScraperFactory:
    """ScraperFactory instantiation and registration tests."""

    def test_create_http_scraper(self) -> None:
        """Factory creates JsonPlaceholder (HTTP) scraper."""
        scraper = ScraperFactory.create("jsonplaceholder")
        assert scraper is not None
        assert isinstance(scraper, Scraper)  # Protocol check

    def test_create_html_scraper(self) -> None:
        """Factory creates Hacker News (HTML) scraper."""
        scraper = ScraperFactory.create("hn")
        assert scraper is not None
        assert isinstance(scraper, Scraper)

    def test_create_browser_scraper(self) -> None:
        """Factory creates Playwright (browser) scraper."""
        scraper = ScraperFactory.create("playwright")
        assert scraper is not None
        assert isinstance(scraper, Scraper)

    def test_invalid_scraper_source(self) -> None:
        """Factory raises ValueError for unregistered source."""
        with pytest.raises(ValueError, match="Unknown scraper source: 'invalid'"):
            ScraperFactory.create("invalid")

    def test_available_sources(self) -> None:
        """Factory lists all registered sources."""
        sources = ScraperFactory.available_sources()
        assert "jsonplaceholder" in sources
        assert "hn" in sources
        assert "playwright" in sources
        assert sources == sorted(sources)  # Verify sorted

    def test_scraper_protocol_compliance(self) -> None:
        """All factory scrapers implement Scraper protocol."""
        for source in ScraperFactory.available_sources():
            scraper = ScraperFactory.create(source)
            assert isinstance(scraper, Scraper)
            assert hasattr(scraper, "scrape")
            assert callable(scraper.scrape)

    def test_factory_creates_new_instance(self) -> None:
        """Factory creates new instance on each call."""
        scraper1 = ScraperFactory.create("jsonplaceholder")
        scraper2 = ScraperFactory.create("jsonplaceholder")
        assert scraper1 is not scraper2  # Different instances
        assert type(scraper1) is type(scraper2)  # Same class
