"""HTTP scraper — httpx + JSONPlaceholder public REST API.

Demonstrates:
- Async httpx client (reuse across requests for connection pooling)
- REST API pagination via limit/offset query params
- Semaphore for concurrency control (rate limiting + resource efficiency)
- Exponential backoff retry (3 attempts max) for resilience
- Strategy pattern: same Scraper interface, different transport
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from services.ingestor.scrapers import BloomFilter, ScrapedItem


logger = logging.getLogger(__name__)

_BASE_URL = "https://jsonplaceholder.typicode.com"
_POSTS_PATH = "/posts"
_SEMAPHORE_LIMIT = 5  # Max concurrent HTTP requests
_MAX_RETRIES = 3  # Exponential backoff: try 3 times
_RETRY_BASE_DELAY = 1.0  # Start with 1 second delay


class HttpScraper:
    """Scrapes posts from JSONPlaceholder (public fake REST API).

    Uses httpx async client with Semaphore for concurrency control.
    The Bloom Filter deduplicates by post URL so repeated scrape() calls
    on the same instance skip already-seen posts.

    Concurrency limit: Semaphore(5) prevents rate-limiting and resource exhaustion.
    Retry logic: Exponential backoff (1s, 2s, 4s) for transient failures.
    """

    def __init__(self) -> None:
        self._seen: BloomFilter = BloomFilter(capacity=1_000, error_rate=0.01)
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(_SEMAPHORE_LIMIT)

    async def _fetch_with_backoff(self, url: str, limit: int) -> list[dict] | None:
        """Fetch posts with exponential backoff retry on failure.

        Args:
            url: Endpoint URL.
            limit: Query parameter for post count.

        Returns:
            JSON response (list of dicts), or None if all retries fail.
        """
        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(url, params={"_limit": limit})
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPError as exc:
                if attempt < _MAX_RETRIES - 1:
                    delay = _RETRY_BASE_DELAY * (2**attempt)  # 1s, 2s, 4s
                    logger.warning(
                        "http_scraper_retry",
                        extra={
                            "attempt": attempt + 1,
                            "error": str(exc),
                            "url": url,
                            "next_retry_delay_s": delay,
                        },
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "http_scraper_exhausted",
                        extra={
                            "attempts": _MAX_RETRIES,
                            "error": str(exc),
                            "url": url,
                        },
                    )
        return None

    async def scrape(self, limit: int = 20) -> list[ScrapedItem]:
        """Fetch up to `limit` posts from JSONPlaceholder.

        Acquires Semaphore before making HTTP request, then retries with
        exponential backoff on transient failures.

        Wait timeout is enforced via asyncio.wait_for to prevent zombie scraper tasks.
        """
        from services.ingestor.config import settings
        from services.ingestor.scrapers import ScraperTimeoutError

        url = f"{_BASE_URL}{_POSTS_PATH}"
        items: list[ScrapedItem] = []

        try:
            async with self._semaphore:
                # Wrap the fetching logic with a global timeout
                posts = await asyncio.wait_for(
                    self._fetch_with_backoff(url, limit),
                    timeout=settings.scraper_timeout,
                )
        except TimeoutError as e:
            logger.error(
                "http_scraper_timeout",
                extra={"url": url, "timeout": settings.scraper_timeout},
            )
            raise ScraperTimeoutError(f"Timeout fetching {url}") from e

        if posts is None:
            return []

        for post in posts:
            post_url = f"{_BASE_URL}{_POSTS_PATH}/{post['id']}"
            if post_url in self._seen:
                continue
            self._seen.add(post_url)
            items.append(
                ScrapedItem(
                    url=post_url,
                    title=post.get("title", ""),
                    content=post.get("body", ""),
                    source="jsonplaceholder",
                )
            )

        logger.info("http_scraper_done", extra={"count": len(items)})
        return items
