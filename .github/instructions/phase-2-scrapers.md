# Phase 2 — Data Scraping with Async Patterns

**Duration**: 2 weeks
**Goal**: Build async scraper (GraphQL + Playwright) with semaphore-based rate limiting
**Success Metric**: 1K+ requests/sec, 99% success rate, <500ms latency on rate-limited endpoints

---

## Core Learning Objective

Master async concurrency patterns: semaphore (concurrency cap), task pooling, backpressure, retry logic, session reuse.

---

## Interview Questions

### Core Q: "Design Async Scraper for 1000 Requests/Sec, Respecting Rate Limits"

**Expected Answer:**

- Async/await for I/O concurrency (network requests are blocking, not CPU)
- Semaphore to cap concurrent requests (e.g., max 100 concurrent, respect target's rate limit)
- Exponential backoff on 429 (rate limited) or 503 (service unavailable)
- HttpX client with connection pooling (reuse TCP connections, faster than creating new)
- Playwright for JS-heavy sites (headless browser automation)
- Session tokens in Redis → avoid re-auth for each request
- DLQ for failed scrapes (after 5 retries)
- Pydantic validators for data shape validation

**Talking Points:**

- Event loop: Single-threaded, coordinates multiple I/O operations. Semaphore prevents blocking.
- Task pooling vs creating new Task per request: Pool (fixed size) prevents memory spike. Unbounded tasks = spiral.
- Rate limit headers: `X-RateLimit-Remaining` → track and pause if near limit.
- Session management: Auth tokens should be cached, reused, refreshed as needed (not re-fetched per request).

---

### Follow-Up: "Compare Async vs Threaded Scraper. When Use Each?"

**Expected Answer:**

- **Async (threads=1, parallelism on I/O waits)**
  - Pros: Lower memory (no thread stack overhead), better for I/O-bound (network), simple code with async/await
  - Cons: Cannot scale on CPU-bound work (single thread)
  - Use case: Web scraping, API calls, database queries → all blocked on I/O

- **Threaded (multiple threads, OS scheduling)**
  - Pros: Can utilize multiple CPU cores, simpler for beginners (synchronous code)
  - Cons: Higher memory per thread, GIL contention if Python CPU work, harder to debug
  - Use case: CPU-bound work (parsing, compression), or legacy sync libraries

- **ProcessPoolExecutor (multiple processes)**
  - Pros: True parallelism (escape GIL), unlimited scale on CPU
  - Cons: High memory, IPC overhead (serialization), not for I/O
  - Use case: Image processing, ML inference, heavy computation

**Talking Points:**

- For web scraping: Async is usually best (no CPU work, just network waits).
- If scraper does heavy HTML parsing → consider async + CPU pool: `asyncio.to_thread(parse_html, html)` offloads to thread pool.
- Semaphore is async-only concept (threads have different concurrency tools like Locks).

---

### Follow-Up: "Scraper Rate-Limited (429). How Detect and Backoff?"

**Expected Answer:**

- Check response headers: `X-RateLimit-Remaining` (how many requests left before reset)
- If `X-RateLimit-Remaining == 0`, pause until `X-RateLimit-Reset` timestamp
- On 429 response: Exponential backoff `2^retry_count` seconds (1s, 2s, 4s, 8s max)
- Jitter: Add random ±10% to backoff (prevents thundering herd if multiple clients)
- Circuit breaker: After 5 consecutive 429s, fail fast and alert (don't hammer recovering service)

**Talking Points:**

- Rate limit strategy varies by provider (token bucket, fixed window, sliding window — hard to guess, so check headers).
- Polite scraping: Respect `User-Agent` restrictions, `robots.txt`, `Retry-After` header.
- DLQ strategy: After max retries (5), send URL + error to DLQ, notify ops, move on (don't block pipeline).

---

## Real life production example — Production-Ready

### Architecture

```text
Redpanda event from Phase 1 (e.g., PricingSource created)
  ↓
app/main.py: route subscribes to records.events.pricing_source_created
  ↓
Trigger: app/scrapers/base.py: async def scrape_price_data(source_id)
  ↓
Semaphore (cap=100 concurrent requests)
  ↓
GraphQL query OR Playwright (JS-heavy) with session reuse
  ↓
Pydantic validation (shape check)
  ↓
Store in database (or DLQ if failed)
  ↓
Prometheus: scraper_requests_total, scraper_latency, scraper_errors, dlq_scraper_size
```

### Implementation Checklist

- [ ] **app/scrapers/base.py** — Semaphore-based scraper

  ```python
  import asyncio
  from httpx import AsyncClient
  from pydantic import BaseModel, ValidationError

  class ScrapedData(BaseModel):
      price: float
      timestamp: datetime
      source: str

  class BaseScraper:
      def __init__(self, max_concurrent: int = 100):
          self.semaphore = asyncio.Semaphore(max_concurrent)
          self.client = AsyncClient(timeout=30.0)  # Reuse

      async def scrape(self, url: str, retry: int = 0) -> dict:
          """Scrape with semaphore, backoff on 429, validate."""
          async with self.semaphore:
              try:
                  response = await self.client.get(url)

                  # Rate limit detection
                  remaining = response.headers.get('X-RateLimit-Remaining', '999')
                  if int(remaining) < 10:
                      retry_after = int(response.headers.get('X-RateLimit-Reset', 60))
                      logger.warning(f"Rate limit near, pausing {retry_after}s")
                      await asyncio.sleep(retry_after)

                  if response.status_code == 429:
                      if retry < 5:
                          backoff = 2 ** retry + random.uniform(-0.1, 0.1) * (2 ** retry)
                          logger.info(f"429 Received, backoff {backoff}s, retry {retry}")
                          await asyncio.sleep(backoff)
                          return await self.scrape(url, retry + 1)
                      else:
                          raise Exception(f"Max retries (5) exceeded for {url}")

                  response.raise_for_status()
                  data = response.json()

                  # Validate shape
                  return ScrapedData(**data).model_dump()

              except ValidationError as e:
                  logger.error(f"Validation failed for {url}: {e}")
                  raise
              except Exception as e:
                  logger.error(f"Scrape failed: {e}")
                  raise
  ```

- [ ] **app/scrapers/graphql_scraper.py** — GraphQL with query batching

  ```python
  async def fetch_pricing_data(sources: list[str]) -> list[dict]:
      """Batch GraphQL query for prices, semaphore-limited."""
      scraper = BaseScraper(max_concurrent=50)  # GraphQL endpoint slower

      tasks = []
      for source in sources:
          query = {"query": f"{{ price(source: \"{source}\") {{ price timestamp }} }}"}
          tasks.append(scraper.scrape_graphql(endpoint, query))

      results = await asyncio.gather(*tasks, return_exceptions=True)

      # Separate successes from errors
      successes = [r for r in results if not isinstance(r, Exception)]
      errors = [r for r in results if isinstance(r, Exception)]

      if errors:
          logger.error(f"Scrape errors: {len(errors)}/{len(tasks)}")
          # Send to DLQ
          for error in errors:
              await dlq.send('scraper.failures', value={'error': str(error)})

      return successes
  ```

- [ ] **app/scrapers/playwright_scraper.py** — JS rendering

  ```python
  from playwright.async_api import async_playwright

  async def scrape_with_javascript(url: str) -> dict:
      """Use Playwright for JS-heavy sites."""
      async with async_playwright() as p:
          browser = await p.chromium.launch(headless=True)
          page = await browser.new_page()
          await page.goto(url, wait_until='networkidle')

          # Extract data
          content = await page.content()
          # Parse with BeautifulSoup or Pydantic model

          await browser.close()
  ```

- [ ] **Exponential Backoff + Jitter**

  ```python
  async def exponential_backoff(retry_count: int, base: float = 1.0, max_wait: float = 60.0):
      """Backoff w/ jitter."""
      wait_time = min(base * (2 ** retry_count), max_wait)
      jitter = random.uniform(-0.1, 0.1) * wait_time
      await asyncio.sleep(wait_time + jitter)
  ```

- [ ] **Session Caching in Redis**

  ```python
  async def get_or_create_session(source_id: str, auth_url: str):
      """Cache auth token in Redis, reuse."""
      cached = await redis.get(f"session:{source_id}")
      if cached:
          return json.loads(cached)

      token = await authenticate(auth_url)
      await redis.setex(f"session:{source_id}", 3600, json.dumps(token))  # 1h TTL
      return token
  ```

- [ ] **docker-compose.yml** additions

  ```yaml
  services:
    playwright-chrome:
      image: mcr.microsoft.com/playwright-python:latest
      # Use if running Playwright in separate service

    # Redis for session caching (already exists, reused)
  ```

- [ ] **Monitoring**

  ```python
  from prometheus_client import Counter, Histogram, Gauge

  scraper_requests = Counter('scraper_requests_total', 'Requests made')
  scraper_latency = Histogram('scraper_latency_seconds', 'Request latency')
  scraper_errors = Counter('scraper_errors_total', 'Request errors', ['status_code'])
  dlq_size = Gauge('dlq_size_scraper', 'Failed scrapes in DLQ')
  rate_limit_waits = Counter('scraper_rate_limit_waits_total', 'Times paused for rate limit')
  ```

---

## Weekly Checklist

### Week 1: Async Scraper + Semaphore

- [ ] BaseScraper class with semaphore (cap=100)
- [ ] HttpX AsyncClient with session reuse (connection pooling)
- [ ] Rate limit detection (X-RateLimit-Remaining header)
- [ ] Exponential backoff on 429 (2^retry + jitter)
- [ ] Pydantic validation for scraped data
- [ ] Unit tests: mock HttpX, test backoff logic (5 retries max)
- [ ] Load test: `asyncio.gather(scrape(url) for url in 1000_urls)` → measure throughput
- [ ] Interview Q: "Async vs threaded scraper?" → Answer drafted
- [ ] Commits: 6–8 (base scraper, httpx setup, retry logic, tests)

### Week 2: Playwright + Monitoring

- [ ] Playwright scraper for JS-heavy sites
- [ ] Session caching in Redis (auth tokens)
- [ ] DLQ for failed scrapes (after 5 retries)
- [ ] Prometheus metrics: requests, latency, errors, DLQ size
- [ ] End-to-end: Phase 1 event → Phase 2 scraper → data stored
- [ ] Load test: 1K+ requests/sec (should hit semaphore limit, not server crush)
- [ ] Interview Q: "Rate limit + backoff strategy?" → Full answer ready
- [ ] Commits: 5–7 (playwright, redis reuse, DLQ, e2e test)
- [ ] Portfolio item + LinkedIn post

---

## Success Metrics

| Metric                 | Target      | How to Measure                                                            |
| ---------------------- | ----------- | ------------------------------------------------------------------------- |
| Throughput             | 1K+ req/sec | `asyncio.gather(*[scrape() for _ in range(10000)])` time → should be ~10s |
| Latency (p99)          | <500ms      | Prometheus histogram p99 < 0.5s                                           |
| Success rate           | 99%         | (total - errors) / total                                                  |
| Concurrent connections | <150        | Monitor via `netstat -an \| grep ESTABLISHED` or Prometheus               |
| Retry logic            | ≤5 per URL  | After 5 backoffs, send to DLQ                                             |
| Session reuse          | 90%+        | Redis hit rate `redis.get(session:*)` / total scrapes                     |
| Commit count           | 11–15       | 1 per feature + tests                                                     |

---

## Gotchas + Fixes

### Gotcha 1: "Semaphore Exhausted, Tasks Blocked"

**Symptom**: Latency spikes to 10s+, throughput drops.
**Cause**: Semaphore cap (100) hit, tasks queue, network I/O takes >3s per connection (slow target).
**Fix**: Increase semaphore if target allows, or reduce timeout (fail fast). Monitor with `asyncio.current_task()` count.

### Gotcha 2: "Connection Pool Exhausted"

**Symptom**: ECONNREFUSED errors after 100+ concurrent requests.
**Cause**: HttpX connection pool default too small, OS runs out of sockets.
**Fix**: Configure pool: `AsyncClient(limits=Limits(max_connections=200, max_keepalive_connections=100))`.

### Gotcha 3: "Playwright Chromium Runs Out of Memory"

**Symptom**: OOM kill, Playwright process dies.
**Cause**: Creating new browser instance per request (heavyweight).
**Fix**: Reuse browser instance, create new page per request (pages are lightweight). Or use pool of browsers.

### Gotcha 4: "Rate Limit Not Detected, Still 429"

**Symptom**: Scraper continues requesting despite 429s, DLQ fills.
**Cause**: Rate limit headers vary by provider (`X-RateLimit-*`, `Retry-After`, `429` response alone).
**Fix**: Add provider-specific detection. Log all 429 responses to understand pattern, then hard-code backoff if headers absent.

---

## Cleanup (End of Phase 2)

```bash
pytest tests/phase_2/ -v  # All scraper tests pass
# Verify DLQ empty after 24h runtime (if filled, debug before cleaning)
```

---

## Metrics to Monitor Ongoing

- `scraper_requests_total`: Should grow steadily
- `scraper_latency_seconds` p99: Alert if > 1s
- `scraper_errors_total`: Alert if > 1% of requests
- `scraper_rate_limit_waits_total`: Trending (should plateau or decrease as rate limits understood)
- `dlq_size_scraper`: Alert if > 50

---

## Next Phase

**Phase 2.5: Docker + CI/CD (Optional Intermediate)**
Containerize scraper, set up GitHub Actions for linting/testing/Docker build. Push to ECR. This bridges Phase 2 into Phase 3.

**Phase 3: AI + Vector Database**
Use scraped data to generate embeddings (OpenAI API or local model), store in Qdrant. Implement semantic search.

**Reference**: Phase 2 stability = can proceed. If scraper hanging on Playwright or rate limits not understood, resolve before Phase 3.
