"""HTML scraper — BeautifulSoup + Hacker News front page.

Demonstrates:
- BeautifulSoup HTML parsing (html.parser, no lxml dependency)
- CSS selector-based extraction
- Semaphore for concurrency control across multiple scraper instances
- Exponential backoff retry (3 attempts max) for resilience
- Strategy pattern: same Scraper interface, different parsing technique
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from bs4 import BeautifulSoup

from services.ingestor.scrapers import BloomFilter, ScrapedItem


logger = logging.getLogger(__name__)

_HN_URL = "https://news.ycombinator.com"
_SEMAPHORE_LIMIT = 5  # Max concurrent HTTP requests
_MAX_RETRIES = 3  # Exponential backoff: try 3 times
_RETRY_BASE_DELAY = 1.0  # Start with 1 second delay


class HtmlScraper:
    """Scrapes story titles and links from Hacker News front page.

    Uses httpx to fetch HTML, then BeautifulSoup to parse the DOM.
    Semaphore enforces concurrency limits to respect rate limits.
    Retry logic: Exponential backoff (1s, 2s, 4s) for transient failures.
    Falls back gracefully on network errors or markup changes.
    """

    def __init__(self) -> None:
        self._seen: BloomFilter = BloomFilter(capacity=500, error_rate=0.01)
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(_SEMAPHORE_LIMIT)

    async def _fetch_with_backoff(self) -> str | None:
        """Fetch HTML with exponential backoff retry on failure.

        Returns:
            HTML content (str), or None if all retries fail.
        """
        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(
                    timeout=15.0,
                    headers={"User-Agent": "data-zoo-scraper/1.0 (educational)"},
                    follow_redirects=True,
                ) as client:
                    response = await client.get(_HN_URL)
                    response.raise_for_status()
                    return response.text
            except httpx.HTTPError as exc:
                if attempt < _MAX_RETRIES - 1:
                    delay = _RETRY_BASE_DELAY * (2**attempt)  # 1s, 2s, 4s
                    logger.warning(
                        "html_scraper_retry",
                        extra={
                            "attempt": attempt + 1,
                            "error": str(exc),
                            "next_retry_delay_s": delay,
                        },
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "html_scraper_exhausted",
                        extra={"attempts": _MAX_RETRIES, "error": str(exc)},
                    )
        return None

    async def scrape(self, limit: int = 20) -> list[ScrapedItem]:
        """Fetch and parse Hacker News front page stories.

        Acquires Semaphore before making HTTP request, then retries with
        exponential backoff on transient failures.

        Args:
            limit: Maximum number of items to return.

        Returns:
            List of ScrapedItem instances.
        """
        items: list[ScrapedItem] = []

        async with self._semaphore:
            html = await self._fetch_with_backoff()

        if html is None:
            return []

        soup = BeautifulSoup(html, "html.parser")
        story_rows = soup.select("tr.athing")

        for row in story_rows[:limit]:
            title_cell = row.select_one("span.titleline > a")
            if title_cell is None:
                continue

            title = title_cell.get_text(strip=True)
            href = title_cell.get("href", "")
            url = href if href.startswith("http") else f"{_HN_URL}/{href}"

            if url in self._seen:
                continue
            self._seen.add(url)

            items.append(
                ScrapedItem(
                    url=url,
                    title=title,
                    content="",
                    source="hn",
                )
            )

        logger.info("html_scraper_done", extra={"count": len(items)})
        return items
