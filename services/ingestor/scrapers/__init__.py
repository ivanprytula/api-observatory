"""Scraper package — Protocol, data models, Bloom Filter, and Factory.

Advanced Python patterns demonstrated:
- Protocol: duck-typed scraper interface (no inheritance required)
- __slots__ via @dataclass(slots=True): memory-efficient scraped item
- BloomFilter: probabilistic URL deduplication before HTTP requests
- Factory pattern: ScraperFactory.create(source) maps names → scrapers
- Strategy pattern: each scraper is a pluggable backend with the same interface
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ScraperTimeoutError(Exception):
    """Raised when a scraper HTTP call exceeds its allotted timeout."""

    pass


# ---------------------------------------------------------------------------
# Scraped item — __slots__ for memory efficiency (high-frequency ingestion)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ScrapedItem:
    """Single scraped document — immutable after creation.

    Uses @dataclass(slots=True) (PEP 681, Python 3.10+) to avoid per-instance
    __dict__ overhead. Matters when ingesting thousands of items per run.
    """

    url: str
    title: str
    content: str
    source: str


# ---------------------------------------------------------------------------
# Bloom Filter — probabilistic URL deduplication
# ---------------------------------------------------------------------------


class BloomFilter:
    """Space-efficient set for URL deduplication before HTTP requests.

    Trade-off: may have false positives (report URL as seen when it's not),
    but never false negatives. Acceptable for scraping: a missed URL costs
    one redundant request; processing a duplicate costs much more.

    Time complexity: O(k) per add/contains, where k = hash_count (~7 for 1% FPR)
    Space complexity: O(m) bits, where m ≈ -n*ln(p) / ln(2)^2
    """

    def __init__(self, capacity: int = 10_000, error_rate: float = 0.01) -> None:
        self._size = self._compute_size(capacity, error_rate)
        self._hash_count = self._compute_hash_count(self._size, capacity)
        self._bits = bytearray(self._size // 8 + 1)

    @staticmethod
    def _compute_size(n: int, p: float) -> int:
        return max(1, int(-n * math.log(p) / (math.log(2) ** 2)))

    @staticmethod
    def _compute_hash_count(m: int, n: int) -> int:
        return max(1, int((m / n) * math.log(2)))

    def _positions(self, item: str) -> list[int]:
        return [
            int(hashlib.sha256(f"{seed}:{item}".encode()).hexdigest(), 16) % self._size
            for seed in range(self._hash_count)
        ]

    def add(self, item: str) -> None:
        """Mark item as seen."""
        for pos in self._positions(item):
            self._bits[pos // 8] |= 1 << (pos % 8)

    def __contains__(self, item: object) -> bool:
        """Return True if item was probably seen before (possible false positive)."""
        if not isinstance(item, str):
            return False
        return all(
            self._bits[pos // 8] & (1 << (pos % 8)) for pos in self._positions(item)
        )


# ---------------------------------------------------------------------------
# Scraper Protocol — duck-typed interface (no inheritance required)
# ---------------------------------------------------------------------------


@runtime_checkable
class Scraper(Protocol):
    """Interface that all scrapers must satisfy.

    @runtime_checkable enables isinstance(obj, Scraper) checks at runtime,
    useful for the factory and dependency injection. Any class with a
    matching scrape() signature automatically satisfies this Protocol.
    """

    async def scrape(self, limit: int = 20) -> list[ScrapedItem]:
        """Fetch and return scraped items up to `limit`."""
        ...


# ---------------------------------------------------------------------------
# ScraperFactory — maps source names to scraper implementations
# ---------------------------------------------------------------------------


class ScraperFactory:
    """Factory that resolves a source name to a concrete Scraper instance.

    Decouples callers from concrete classes — adding a new scraper only
    requires registering it here, not changing router or storage code.
    """

    _registry: dict[str, type] = {}

    @classmethod
    def register(cls, name: str, klass: type) -> None:
        """Register a scraper class under a source name."""
        cls._registry[name] = klass

    @classmethod
    def create(cls, source: str) -> Scraper:
        """Instantiate a scraper for `source`.

        Args:
            source: Registered scraper name (e.g., 'jsonplaceholder', 'hn', 'playwright').

        Returns:
            A concrete Scraper instance.

        Raises:
            ValueError: If source is not registered.
        """
        klass = cls._registry.get(source)
        if klass is None:
            available = sorted(cls._registry)
            raise ValueError(
                f"Unknown scraper source: {source!r}. Available: {available}"
            )
        return klass()

    @classmethod
    def available_sources(cls) -> list[str]:
        """Return all registered source names."""
        return sorted(cls._registry)


# ---------------------------------------------------------------------------
# Lazy registration — executed after concrete classes are imported
# ---------------------------------------------------------------------------


def _register_scrapers() -> None:
    try:
        from services.ingestor.scrapers.html_scraper import HtmlScraper
    except ModuleNotFoundError:
        HtmlScraper = None

    try:
        from services.ingestor.scrapers.browser_scraper import BrowserScraper
    except ModuleNotFoundError:
        BrowserScraper = None

    from services.ingestor.scrapers.http_scraper import HttpScraper

    ScraperFactory.register("jsonplaceholder", HttpScraper)
    if HtmlScraper is not None:
        ScraperFactory.register("hn", HtmlScraper)
    if BrowserScraper is not None:
        ScraperFactory.register("playwright", BrowserScraper)


_register_scrapers()
