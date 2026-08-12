# Pillar 7: Data & ETL

Track: E — Archive and Historical Snapshots

**Tier**: Middle (🟡) — valuable add-on
**Project**: Differentiates in data-heavy roles (DataOX, Fornova, ETL)

---

## Middle Tier (🟡)

### Pandas Fundamentals

**Reading/writing**:

```python
import pandas as pd

# Read CSV
df = pd.read_csv("data.csv")

# Filter
df_filtered = df[df["price"] > 100]

# Transform
df["price_usd"] = df["price"] * 1.1

# Group and aggregate
summary = df.groupby("category").agg({"price": ["mean", "max"], "quantity": "sum"})

# Write
df.to_csv("output.csv", index=False)
df.to_parquet("output.parquet")
```

---

### ETL Pattern

**Extract → Transform → Load** as three pure functions:

```python
async def extract(source_url: str) -> list[dict]:
    """Download data from source."""
    async with httpx.AsyncClient() as client:
        response = await client.get(source_url)
        return response.json()

def transform(raw_data: list[dict]) -> list[dict]:
    """Clean and normalize."""
    cleaned = []
    for item in raw_data:
        if not item.get("id"):
            continue  # Skip invalid
        cleaned.append({
            "id": item["id"],
            "name": item.get("name", "").strip(),
            "price": float(item.get("price", 0)),
        })
    return cleaned

async def load(db: AsyncSession, observations: list[dict]) -> int:
    """Insert into database idempotently."""
    stmt = insert(Observation).values(observations).on_conflict_do_nothing()
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount

# Pipeline
async def run_etl():
    raw = await extract("https://api.example.com/data")
    clean = transform(raw)
    loaded = await load(db, clean)
    print(f"Loaded {loaded} observations")
```

**Idempotent loads**: `ON CONFLICT DO UPDATE` or truncate+reload

- Re-running same ETL = no duplicates
- Key for batch jobs that might fail and retry

**Incremental refresh** (don't re-process all data):

```python
async def get_last_run_time(db: AsyncSession) -> datetime | None:
    """Get timestamp of last successful ETL."""
    result = await db.scalar(
        select(func.max(ETLRun.completed_at))
    )
    return result

async def extract_since(source_url: str, since: datetime) -> list[dict]:
    """Only fetch observations modified after `since`."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            source_url,
            params={"modified_after": since.isoformat()}
        )
        return response.json()

# Main
last_run = await get_last_run_time(db)
raw = await extract_since("...", since=last_run or datetime(2000, 1, 1))
clean = transform(raw)
await load(db, clean)
```

---

### Queues / Task Orchestration

**Celery + Cache** (heavy but battle-tested):

```python
from celery import Celery

app = Celery("data_pipeline", broker="redis://127.0.0.1:6379")

@app.task
def process_observation(observation_id: int):
    """Long-running task."""
    # Can be retried automatically on failure
    pass

# Queue task
process_observation.delay(123)

# Monitor with Flower: flower app:app
```

**arq** (simpler, async-native):

```python
from arq import create_pool

async def process_record(record_id: int):
    db = await get_db()
    record = await db.get(Record, record_id)
    # Do work
    return {"processed": record_id}

async def main():
    cache = await create_pool("redis://localhost")
    job = await cache.enqueue(process_record, 123)
    result = await job.result()
    print(result)
```

---

### Scraping (DataOX/Fornova-style)

**httpx + BeautifulSoup**:

```python
import httpx
from bs4 import BeautifulSoup

async def scrape_page(url: str) -> list[dict]:
    """Scrape data from HTML."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)

    soup = BeautifulSoup(response.text, "html.parser")
    items = []

    for div in soup.select("div.product"):
        items.append({
            "name": div.select_one("h2").text.strip(),
            "price": float(div.select_one(".price").text.replace("$", "")),
            "url": div.find("a")["href"],
        })

    return items
```

**Playwright** (headless browser for JavaScript):

```python
from playwright.async_api import async_playwright

async def scrape_dynamic(url: str) -> list[dict]:
    """Scrape JavaScript-rendered page."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        await page.goto(url)
        await page.wait_for_selector("div.product", timeout=5000)

        html = await page.content()

        await browser.close()

    # Now parse with BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    # ... extract data
```

**Anti-bot basics**:

- Randomize delays: `await asyncio.sleep(random.uniform(1, 3))`
- Rotate user-agents (see `fake-useragent` library)
- CAPTCHA: use 2captcha API
- Proxy rotation: `httpx.AsyncClient(proxies="socks5://proxy:port")`

---

## You Should Be Able To

✅ Read/write CSV, JSON, Parquet with pandas
✅ Filter, group, aggregate with pandas
✅ Design idempotent ETL pipeline (E→T→L)
✅ Implement watermark column for incremental loads
✅ Queue long-running tasks with arq or Celery
✅ Scrape HTML with BeautifulSoup
✅ Scrape JavaScript with Playwright
✅ Handle anti-bot challenges (delays, user-agents, proxies)
✅ Explain why you'd use pandas vs raw SQL

---

## References

- [Pandas Docs](https://pandas.pydata.org/)
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/)
- [Playwright Python](https://playwright.dev/python/)
- [Celery](https://docs.celeryproject.io/)
- [arq](https://arq-docs.helpmanual.io/)
- [fake-useragent](https://github.com/fake-useragent/fake-useragent)

---

## Checklist — Pillar 7: Data & ETL

### Foundation 🟢

- [ ] Explain the three ETL stages: Extract, Transform, Load — with an example
  - [ ] Know: Extract = fetch raw; Transform = validate/clean; Load = persist
- [ ] Use Pandas: `pd.read_json`, `DataFrame.dropna()`, `.astype()`, `.to_dict("records")`
- [ ] Fetch data with `httpx.AsyncClient` and handle non-200 status codes
- [ ] Parse HTML with BeautifulSoup: `soup.select()`, `soup.find()`, `.get_text()`

### Middle 🟡

- [ ] Use `asyncio.Semaphore` to cap concurrent scraping requests
  - [ ] Know why `asyncio.gather` with no limit can hammer a target server
- [ ] Implement exponential backoff with jitter for HTTP retries
- [ ] Validate and transform data with Pydantic schemas as ETL transformers
- [ ] Explain URL deduplication strategies: Cache SET vs Bloom Filter
  - [ ] Know: Bloom Filter = probabilistic, memory-efficient, no false negatives
- [ ] Use Playwright async API for JavaScript-rendered pages
  - [ ] Know when to use Playwright over `httpx`: JS-rendered content, login flows

### Senior 🔴

- [ ] Compare Celery vs `arq` for async task queues with trade-offs
  - [ ] Celery: Cache or RabbitMQ broker, mature, large ecosystem
  - [ ] arq: asyncio-native, simpler, Cache-only
- [ ] Design an incremental ETL pipeline vs full reload — when each applies
  - [ ] Incremental: `WHERE updated_at > last_run`; full reload: simpler but expensive at scale
- [ ] Handle schema evolution in ETL without breaking downstream consumers
- [ ] Implement distributed URL assignment with consistent hashing (Kafka partitions)

### Pre-Interview Refresh ✏️

- [ ] Explain Extract-Transform-Load with a concrete example from this project
- [ ] Why `asyncio.Semaphore` instead of unlimited `asyncio.gather` for scraping?
- [ ] What is a Bloom Filter? Can it have false negatives?
- [ ] When do you use Playwright instead of `httpx`?
- [ ] Celery vs `arq` — which is better for an existing asyncio codebase and why?
