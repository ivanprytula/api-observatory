"""Browser scraper — Playwright async for JS-rendered content.

Demonstrates:
- Playwright async API for headless browser automation
- Handling JavaScript-rendered pages that httpx cannot parse
- Semaphore for concurrency control (browser processes are expensive)
- Exponential backoff retry (3 attempts max) for browser failures
- Strategy pattern: same Scraper interface, full browser transport
- Graceful degradation when Playwright browsers are not installed

Setup (run once): playwright install chromium
"""

from __future__ import annotations

import asyncio
import logging

from services.ingestor.scrapers import BloomFilter, ScrapedItem


logger = logging.getLogger(__name__)

_TARGET_URL = "https://quotes.toscrape.com/js/"
_SEMAPHORE_LIMIT = 3  # Lower limit for browser (more expensive than HTTP)
_MAX_RETRIES = 3  # Exponential backoff: try 3 times
_RETRY_BASE_DELAY = 1.0  # Start with 1 second delay


class BrowserScraper:
    """Scrapes quotes from quotes.toscrape.com (JS-rendered demo site).

    Uses Playwright headless Chromium to wait for the JS to render DOM,
    then extracts quote text and author. Uses Semaphore to limit concurrent
    browser processes (expensive resource). Falls back gracefully on
    Playwright not being installed or the browser launch failing.

    Note: Requires `playwright install chromium` before first use.
    In Docker, add `RUN playwright install --with-deps chromium` to Dockerfile.
    """

    def __init__(self) -> None:
        self._seen: BloomFilter = BloomFilter(capacity=500, error_rate=0.01)
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(_SEMAPHORE_LIMIT)

    async def _fetch_with_backoff(self) -> list[ScrapedItem] | None:
        """Launch browser and extract quotes with exponential backoff retry.

        Returns:
            List of ScrapedItem instances, or None if all retries fail.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning(
                "playwright_not_installed",
                extra={"hint": "run: playwright install chromium"},
            )
            return None

        for attempt in range(_MAX_RETRIES):
            try:
                async with async_playwright() as pw:
                    browser = await pw.chromium.launch(headless=True)
                    page = await browser.new_page()

                    await page.goto(
                        _TARGET_URL, wait_until="networkidle", timeout=30_000
                    )

                    quote_elements = await page.query_selector_all(".quote")
                    items: list[ScrapedItem] = []

                    for element in quote_elements:
                        text_el = await element.query_selector(".text")
                        author_el = await element.query_selector(".author")

                        text = await text_el.inner_text() if text_el else ""
                        author = await author_el.inner_text() if author_el else ""

                        url = f"{_TARGET_URL}#{hash(text) & 0xFFFFFF:06x}"
                        if url not in self._seen:
                            self._seen.add(url)
                            items.append(
                                ScrapedItem(
                                    url=url,
                                    title=author,
                                    content=text,
                                    source="playwright",
                                )
                            )

                    await browser.close()
                    return items

            except Exception as exc:
                if attempt < _MAX_RETRIES - 1:
                    delay = _RETRY_BASE_DELAY * (2**attempt)  # 1s, 2s, 4s
                    logger.warning(
                        "browser_scraper_retry",
                        extra={
                            "attempt": attempt + 1,
                            "error": str(exc),
                            "next_retry_delay_s": delay,
                        },
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "browser_scraper_exhausted",
                        extra={"attempts": _MAX_RETRIES, "error": str(exc)},
                    )
        return None

    async def scrape(self, limit: int = 20) -> list[ScrapedItem]:
        """Fetch and render JS page, then extract quotes.

        Acquires Semaphore before launching browser to limit concurrent
        browser processes (expensive resource). Retries with exponential
        backoff on transient failures.

        Args:
            limit: Maximum number of items to return.

        Returns:
            List of ScrapedItem instances.
        """
        async with self._semaphore:
            items = await self._fetch_with_backoff()

        if items is None:
            return []

        logger.info("browser_scraper_done", extra={"count": len(items)})
        return items[:limit]
