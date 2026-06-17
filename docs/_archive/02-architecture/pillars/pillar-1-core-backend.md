# Pillar 1: Core Backend (Python + FastAPI)

Track: E — Archive and Historical Snapshots

**Tier**: Foundation (🟢) + Middle (🟡) + Senior (🔴)
**Project**: api-observatory (previously named data-pipeline-async)
**Building in**: `api-observatory` / `services/ingestor/`

---

## Foundation (🟢) — Unlocks 90-95% of Junior/Middle Positions

### Python 3.x Internals You Must Own

#### OOP: Inheritance, Dunders, Dataclasses, ABCs

**What it is**:

- `__init__`, `__str__`, `__repr__`, `__eq__`, `__call__`, `__enter__`/`__exit__`
- Single + multiple inheritance, MRO (Method Resolution Order)
- `dataclasses.dataclass` for simple model classes
- `abc.ABC` / `@abstractmethod` for enforcing contracts

**When to use**:

- `dataclass`: When you need a class that's mostly data (fields + optional methods)
- `ABC`: When you want subclasses to implement specific methods
- Dunders: When you want to make your class behave like built-ins (list, dict, context manager)

**Example**:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

class Record(ABC):
    """Abstract base for all observations."""
    @abstractmethod
    def validate(self) -> bool:
        pass

@dataclass
class APIRecord(Record):
    source: str
    timestamp: str
    data: dict

    def validate(self) -> bool:
        return bool(self.source and self.timestamp and self.data)

    def __repr__(self) -> str:
        return f"APIRecord(source={self.source}, ts={self.timestamp[:10]})"
```

**[gotcha]**: MRO can be surprising with multiple inheritance. Run `MyClass.__mro__` to see order.

---

#### `asyncio`: Event Loop, `await`, `Task`, `gather`, `Semaphore`, `shield`

**What it is**:

- Single-threaded concurrency: one OS thread, many coroutines
- `async def` = coroutine function (returns coroutine object, not result)
- `await` = pause here, let event loop run other coroutines
- `Task` = scheduled coroutine in event loop
- `asyncio.gather()` = fan-out: run multiple tasks concurrently, wait for all
- `Semaphore` = limit concurrent access (e.g., only 5 concurrent DB connections)
- `shield()` = protect task from cancellation

**When to use**:

- Async for **I/O-bound** tasks (DB queries, HTTP calls, file reads)
- NOT for CPU-bound (use multiprocessing instead)
- `gather` when you have multiple independent operations
- `Semaphore` to prevent overwhelming resources (DB connection pool)

**Example**:

```python
import asyncio

async def fetch_user(user_id: int) -> dict:
    """Simulate async DB fetch."""
    await asyncio.sleep(0.1)  # Simulate I/O
    return {"id": user_id, "name": f"User {user_id}"}

async def fetch_many_users(user_ids: list[int]) -> list[dict]:
    """Fan-out: fetch all concurrently."""
    tasks = [fetch_user(uid) for uid in user_ids]
    return await asyncio.gather(*tasks)
    # Without gather: would take len(user_ids) * 0.1s
    # With gather: takes 0.1s (all concurrent)

async def fetch_with_limit(user_ids: list[int], max_concurrent: int = 5) -> list[dict]:
    """Limit concurrency with Semaphore."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def bounded_fetch(uid: int) -> dict:
        async with semaphore:
            return await fetch_user(uid)

    return await asyncio.gather(*[bounded_fetch(uid) for uid in user_ids])
```

**[gotcha]**: Blocking sync code (like `time.sleep()`) blocks the entire event loop. Use `asyncio.sleep()` instead.

**[gotcha]**: Forgetting `await` on a coroutine = it never runs, just gets created then garbage collected.

---

#### Type Hints: Fully Annotated Code, Generics, `TypeAlias`, `Annotated`

**What it is**:

- `def foo(x: int) -> str:` = type hints for static analysis (mypy, pylance)
- `List[int]` (old) vs `list[int]` (Python 3.9+) — prefer latter
- `Optional[T]` = `T | None`
- `TypeAlias` = give a name to a complex type
- `Annotated[T, metadata]` = attach extra info (validation rules, FastAPI dependencies)

**When to use**:

- Every function signature (parameters + return type)
- Every variable that's not obvious (especially with unions)
- `Annotated` for FastAPI routes (more on Pillar 3)

**Example**:

```python
from typing import TypeAlias, Annotated

# Old way (confusing)
def process(observations):  # What type is observations?
    ...

# New way (clear)
UserID: TypeAlias = int
RecordList: TypeAlias = list[dict]

def process(observations: RecordList) -> dict:
    """Process a list of observations, return summary stats."""
    return {
        "count": len(observations),
        "sources": set(r.get("source") for r in observations),
    }

# With Annotated (FastAPI uses this)
PaginationLimit = Annotated[int, "limit results to N rows"]

def list_observations(limit: PaginationLimit = 10) -> RecordList:
    """List observations, max 10 per page."""
    ...
```

**[gotcha]**: Type hints are **not** enforced at runtime. They're for static checkers. A function doesn't error if you pass wrong type; it just doesn't type-check.

---

### FastAPI

#### Routes, Path/Query/Body Params, Status Codes

**What it is**:

- `@app.get("/path")` = define route
- Path param: `/users/{id}` → captured in function arg
- Query param: `?limit=10` → separate function arg
- Body param: JSON payload → function arg with type hint

**When to use**:

- Path: resource IDs (`/users/{user_id}`)
- Query: filters, pagination, metadata (`?limit=10&source=api.example.com`)
- Body: structured input (schemas, Pydantic models)

**Example**:

```python
from fastapi import FastAPI, status
from pydantic import BaseModel

app = FastAPI()

class RecordRequest(BaseModel):
    source: str
    timestamp: str
    data: dict

@app.get("/observations/{observation_id}", status_code=status.HTTP_200_OK)
async def get_observation(observation_id: int) -> dict:
    """Get by path param."""
    return {"id": observation_id}

@app.get("/observations", status_code=status.HTTP_200_OK)
async def list_observations(limit: int = 10, source: str | None = None) -> dict:
    """Query params for filtering."""
    return {"limit": limit, "source": source}

@app.post("/observations", status_code=status.HTTP_201_CREATED)
async def create_observation(observation: RecordRequest) -> dict:
    """Body param: JSON payload."""
    return {"created": observation.model_dump()}
```

**[gotcha]**: Query params without defaults are optional. Add default or `| None`.

---

#### `Annotated` Dependencies + `Depends` — The Modern DI Pattern

**What it is**:

- `Depends()` = inject a function's return value into route
- `Annotated[Type, Depends(func)]` = explicit dependency (preferred)
- Allows reusable logic (DB session, auth, pagination)

**When to use**:

- DB session injection (`Depends(get_db)`)
- Auth checks (`Depends(get_current_user)`)
- Shared validation/transformation

**Example** (from api-observatory):

```python
from typing import Annotated
from fastapi import Depends

async def get_db() -> AsyncSession:
    """Dependency: provide DB session."""
    async with AsyncSessionLocal() as session:
        yield session

DbDep = Annotated[AsyncSession, Depends(get_db)]

@app.get("/api/v1/observations")
async def list_observations(db: DbDep, limit: int = 10) -> dict:
    """DB session is injected automatically."""
    observations = await crud.list_observations(db, limit=limit)
    return {"observations": observations}
```

**[gotcha]**: FastAPI caches dependency results per request. If you call `get_db` twice in same request, you get same session.

---

#### `lifespan` Context Manager (Startup/Shutdown, Replaces `@on_event`)

**What it is**:

- `@asynccontextmanager` decorator
- Everything before `yield` = startup
- Everything after `yield` = shutdown
- Replaces deprecated `@app.on_event("startup")`

**When to use**:

- Create database pool on startup
- Migrate schema before server starts
- Close connections on shutdown

**Example**:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    # Startup
    print("Starting up...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield  # App runs here

    # Shutdown
    print("Shutting down...")
    await engine.dispose()

app = FastAPI(lifespan=lifespan)
```

**[gotcha]**: Exceptions during startup prevent app from starting. Exceptions during shutdown get logged but don't crash app.

---

### Pydantic v2

#### `BaseModel`, `Field`, `model_config = {"from_attributes": True}`

**What it is**:

- `BaseModel` = parent class for all schemas
- `Field()` = configure individual field (validation, docs, default)
- `model_config` = class-level settings

**When to use**:

- Every API request/response (request = input validation, response = serialization)
- `Field(description="...")` for OpenAPI docs
- `model_config = {"from_attributes": True}` when reading from ORM models

**Example**:

```python
from pydantic import BaseModel, Field

class RecordRequest(BaseModel):
    """API request to create a observation."""
    source: str = Field(..., min_length=1, description="Data source identifier")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    data: dict = Field(default_factory=dict, description="Arbitrary JSON data")

class RecordResponse(BaseModel):
    """API response (serialized from ORM Record model)."""
    model_config = {"from_attributes": True}

    id: int
    source: str
    timestamp: str
    data: dict
    created_at: str
```

**[gotcha]**: `from_attributes=True` allows reading from SQLAlchemy ORM models. Without it, you must manually convert to dict.

---

#### `field_validator`, `model_validator`, `@computed_field`

**What it is**:

- `@field_validator("field_name")` = validate single field before storing
- `@model_validator(mode="after")` = validate entire model after parsing
- `@computed_field` = derived field (computed on access)

**When to use**:

- Field validator: check if timestamp is valid ISO 8601
- Model validator: check cross-field constraints (if status='processed', then processed_at must be set)
- Computed field: read-only fields like `age_days` computed from `created_at`

**Example**:

```python
from pydantic import BaseModel, field_validator, model_validator

class Record(BaseModel):
    source: str
    timestamp: str
    processed: bool = False
    processed_at: str | None = None

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """Ensure timestamp is valid ISO 8601."""
        try:
            from datetime import datetime
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("Invalid ISO 8601 timestamp")
        return v

    @model_validator(mode="after")
    def check_processed_constraint(self) -> "Record":
        """If processed=True, processed_at must be set."""
        if self.processed and not self.processed_at:
            raise ValueError("processed=True requires processed_at")
        return self
```

**[gotcha]**: Field validators run during parsing (before model instantiation). Model validators run after.

---

### Testing

#### `pytest`: Fixtures, Parametrize, `tmp_path`

**What it is**:

- `@pytest.fixture` = reusable test setup
- `@pytest.mark.parametrize` = run test with multiple inputs
- `tmp_path` = temporary directory per test

**When to use**:

- Fixtures: shared DB session, test client, seed data
- Parametrize: test same logic with different inputs
- tmp_path: test file operations without polluting real filesystem

**Example**:

```python
import pytest

@pytest.fixture
async def client(db_session):
    """Fixture: test client with overridden DB."""
    from httpx import AsyncClient
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_db] = lambda: db_session
    yield AsyncClient(app=app, base_url="http://test")
    app.dependency_overrides.clear()

@pytest.mark.parametrize("source,expected", [
    ("api.example.com", 200),
    ("", 422),  # Empty source fails validation
])
async def test_create_observation(client, source, expected):
    """Test with multiple inputs."""
    response = await client.post("/observations", json={"source": source, ...})
    assert response.status_code == expected

async def test_file_operations(tmp_path):
    """Test with temporary directory."""
    test_file = tmp_path / "test.json"
    test_file.write_text('{"key": "value"}')
    assert test_file.read_text() == '{"key": "value"}'
```

**[gotcha]**: `TestClient` is sync; for async routes, use `AsyncClient` + `pytest-asyncio`.

---

#### `pytest-asyncio` (`asyncio_mode = "auto"`)

**What it is**:

- Plugin that runs async tests
- `asyncio_mode = "auto"` in `pyproject.toml` = auto-detect async tests
- No need for `@pytest.mark.asyncio` if mode=auto

**When to use**:

- Writing async test functions (which you are with FastAPI)

**Example** (pyproject.toml):

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

Then write tests:

```python
async def test_list_observations(client):  # No decorator needed
    response = await client.get("/observations")
    assert response.status_code == 200
```

**[gotcha]**: Without `asyncio_mode = "auto"`, you must add `@pytest.mark.asyncio` to every async test.

---

#### `httpx.AsyncClient` + `ASGITransport` for Integration Tests

**What it is**:

- `AsyncClient` = async HTTP client for testing
- `ASGITransport` = talks directly to FastAPI app (no network)
- Faster than spinning up real server

**When to use**:

- Integration tests (test full request → route → DB → response)

**Example**:

```python
from httpx import AsyncClient, ASGITransport

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

async def test_create_observation(client):
    response = await client.post("/observations", json={
        "source": "test",
        "timestamp": "2026-04-02T15:00:00",
        "data": {}
    })
    assert response.status_code == 201
    assert response.json()["id"] > 0
```

---

#### `dependency_overrides` to Swap DB for `aiosqlite` in Tests

**What it is**:

- `app.dependency_overrides[get_db] = test_db_session`
- Replaces real dependency with test mock

**When to use**:

- Swap PostgreSQL → in-memory SQLite for tests (no Docker needed)

**Example** (conftest.py):

```python
@pytest.fixture
async def test_db():
    """In-memory SQLite for tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal(engine) as session:
        yield session

    await engine.dispose()

@pytest.fixture
async def client(test_db):
    app.dependency_overrides[get_db] = lambda: test_db
    yield AsyncClient(app=app)
    app.dependency_overrides.clear()
```

**[gotcha]**: SQLite single connection = all tests share same DB. Use `StaticPool` to ensure transactions are isolated.

---

#### Coverage: `pytest --cov=app` ≥ 80%

**What it is**:

- Measures % of code executed by tests
- `--cov=app` = coverage for `app/` directory

**When to use**:

- CI gate: fail if coverage drops below 80%

**Example**:

```bash
uv run pytest tests/ --cov=app --cov-report=html
```

Then open `htmlcov/index.html` to see which lines were executed.

---

## Middle Tier (🟡) — Unlocks 90%+ Middle-Level Positions

### Concurrency Patterns

#### `asyncio.gather` Fan-Out: Batch-Write 100 Records Concurrently

**What it is**:

- Run multiple coroutines concurrently
- Wait for all to finish
- Returns list of results

**When to use**:

- Bulk inserts (100 observations, run 10 at a time)
- Fan-out reads (fetch user, profile, posts concurrently)

**Example** (add to api-observatory):

```python
async def create_observations_batch_concurrent(
    db: AsyncSession,
    observations: list[RecordRequest],
    max_concurrent: int = 10,
) -> list[Record]:
    """Create multiple observations concurrently with fan-out."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def create_one(observation: RecordRequest) -> Record:
        async with semaphore:
            return await crud.create_observation(db, observation)

    return await asyncio.gather(*[create_one(r) for r in observations])
    # With 100 observations + 10 concurrent:
    # - Sequential: 10 DB round-trips
    # - With gather: ~1-2 round-trips (batched)
```

**[gotcha]**: All tasks share same `get_db` session. Make sure session is created once, reused.

---

#### `asyncio.Semaphore` to Cap Fan-Out Without Pool Exhaustion

**What it is**:

- Token bucket: only N tasks can run simultaneously
- `async with semaphore:` acquires token
- Token released when block exits

**When to use**:

- Prevent overwhelming DB connection pool
- Rate-limit external API calls

**Example**:

```python
async def fetch_many_users(user_ids: list[int]) -> list[dict]:
    """Fetch up to 20 concurrently, then throttle."""
    semaphore = asyncio.Semaphore(20)

    async def bounded_fetch(uid: int) -> dict:
        async with semaphore:
            # Max 20 concurrent DB queries
            return await fetch_user(uid)

    return await asyncio.gather(*[bounded_fetch(uid) for uid in user_ids])
```

**[gotcha]**: Semaphore + connection pool size should align. If pool_size=10 and semaphore=50, you'll get "too many connections" errors.

---

#### Retry with Exponential Backoff + Jitter — Implement via `tenacity`

**What it is**:

- Retry failed operation with exponential delays: 1s, 2s, 4s, 8s...
- Add random jitter to prevent thundering herd
- Max retries to prevent infinite loops

**When to use**:

- External API calls (flaky networks)
- DB operations (temporary locks)
- NOT for validation errors (they won't succeed with retries)

**Example**:

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
async def fetch_external_api(url: str) -> dict:
    """Retry with exponential backoff: 1s, 2s, 4s."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()
```

**[gotcha]**: Retryable vs non-retryable errors. 429 (rate limit) = retry. 400 (bad request) = don't retry.

---

### API Patterns

#### Cursor-Based Pagination (Replace `skip`/`limit` with Opaque Cursor)

**What it is**:

- Old way: `?offset=100&limit=10` — breaks if data inserted between pages
- New way: `?cursor=abc123xyz&limit=10` — cursor = encoded position, stable across inserts

**When to use**:

- Stable pagination over mutating data
- More efficient than offset (no need to count rows)

**Example**:

```python
import base64
import json

def encode_cursor(observation_id: int) -> str:
    """Encode observation ID as opaque cursor."""
    data = json.dumps({"id": observation_id})
    return base64.b64encode(data.encode()).decode()

def decode_cursor(cursor: str) -> int:
    """Decode cursor back to observation ID."""
    data = base64.b64decode(cursor.encode()).decode()
    return json.loads(data)["id"]

@app.get("/api/v1/observations")
async def list_observations(
    db: DbDep,
    limit: int = 10,
    cursor: str | None = None,
) -> dict:
    """List observations using cursor pagination."""
    query = select(Record).order_by(Record.id)

    if cursor:
        after_id = decode_cursor(cursor)
        query = query.where(Record.id > after_id)

    observations = await db.scalars(query.limit(limit + 1))
    observations = list(observations)  # Eager load

    has_more = len(observations) > limit
    observations = observations[:limit]

    next_cursor = None
    if has_more:
        next_cursor = encode_cursor(observations[-1].id)

    return {
        "observations": [r.to_dict() for r in observations],
        "next_cursor": next_cursor,
    }
```

**[gotcha]**: Cursor must be stable. If you use `created_at` and two observations have same timestamp, cursor breaks. Use `id` instead.

---

#### Idempotent Upsert (`ON CONFLICT DO NOTHING` or `MERGE`)

**What it is**:

- `INSERT ... ON CONFLICT DO NOTHING` = if duplicate key, silently skip
- `INSERT ... ON CONFLICT DO UPDATE` = if duplicate, update instead
- Makes endpoint safe to call multiple times

**When to use**:

- APIs that might be called twice (network retry, double-click)
- ETL pipelines (re-run same batch → no duplicates)

**Example**:

```python
from sqlalchemy import insert, values

async def create_observation_idempotent(
    db: AsyncSession,
    source: str,
    timestamp: str,
    data: dict,
) -> Record:
    """Create or get existing (by source + timestamp)."""
    # Assume source + timestamp is unique
    stmt = insert(Record).values(
        source=source,
        timestamp=timestamp,
        data=data,
    ).on_conflict_do_nothing()

    await db.execute(stmt)
    await db.commit()

    # Now fetch to return
    result = await db.execute(
        select(Record).where(
            (Record.source == source) & (Record.timestamp == timestamp)
        )
    )
    return result.scalar_one()
```

**[gotcha]**: `on_conflict_do_nothing()` = returns nothing on conflict. You must refetch if you need the ID.

---

#### Rate Limiting: `slowapi` + Cache Backend

**What it is**:

- Limit requests per IP/user (e.g., 100 requests/minute)
- Return `429 Too Many Requests` when exceeded

**When to use**:

- Public APIs (prevent abuse)
- Prevent brute force on `/login`

**Example**:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="redis://127.0.0.1:6379",  # Persists across app restarts
)
app.state.limiter = limiter

@app.post("/api/v1/observations")
@limiter.limit("100/minute")  # 100 requests/minute per IP
async def create_observation(observation: RecordRequest, db: DbDep) -> dict:
    return await crud.create_observation(db, observation)
```

Test it:

```python
async def test_rate_limit():
    for i in range(101):
        response = await client.post("/observations", json={...})
        if i < 100:
            assert response.status_code == 201
        else:
            assert response.status_code == 429  # Rate limited
```

**[gotcha]**: Without Cache, limiter doesn't persist across restarts. Use in-memory limiter for dev, Cache for prod.

---

#### Request ID Middleware (`X-Request-ID` Header, UUID Injected into Every Log)

**What it is**:

- Generate UUID for each request
- Include in every log entry
- Client can include in request to correlate with logs

**When to use**:

- Every production API (essential for debugging)

**Example**:

```python
from uuid import uuid4
import logging
from fastapi import Request

logger = logging.getLogger(__name__)

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Middleware: inject request ID into every log."""
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    request.state.request_id = request_id

    logger.info("request_start", extra={
        "cid": request_id,
        "method": request.method,
        "path": request.url.path,
    })

    response = await call_next(request)

    logger.info("request_end", extra={
        "cid": request_id,
        "status": response.status_code,
        "duration_ms": response.headers.get("X-Process-Time", "?"),
    })

    response.headers["X-Request-ID"] = request_id
    return response
```

**[gotcha]**: Must inject into logging context so every logger.info() automatically includes it. Use `contextvars` for thread safety.

---

#### Health Check That Pings DB (`SELECT 1`) — Not Just `{"status": "ok"}`

**What it is**:

- `/health` endpoint that returns `{"status": "ok"}` if DB is reachable
- Prevents 🚨 "app is running but cannot query DB" scenario

**When to use**:

- Load balancers use `/health` to decide if instance is alive
- Used by Kubernetes liveness probes

**Example**:

```python
@app.get("/health")
async def health_check(db: DbDep) -> dict:
    """Health check: verify DB connectivity."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "ok"}
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": f"failed: {str(e)}",
        }, 503  # Service Unavailable
```

**[gotcha]**: Liveness probes should be fast. If `SELECT 1` takes >1s, consider a separate lightweight endpoint.

---

## Senior Differentiators (🔴)

### Inter-Service Communication: gRPC Basics or ZeroMQ

**What it is**:

- gRPC: binary protocol, HTTP/2, strongly typed (protobuf)
- ZeroMQ: pub/sub, request/reply, low-latency messaging

**Prerequisites**:

- Comfortable with HTTP APIs (Pillar 1 Foundation)
- Understanding of message serialization (JSON → more efficient binary)

**When to use**:

- gRPC: internal service-to-service (lower latency than REST+JSON)
- ZeroMQ: event streaming, async queues

---

### Custom ASGI Middleware Stack; Profiling with `py-spy` or `Pyinstrument`

**What it is**:

- ASGI middleware = intercept every request/response
- `py-spy` = sample profiler (CPU, memory)
- `Pyinstrument` = deterministic profiler (exact call trees)

**When to use**:

- Custom middleware: auth, logging, request transformation
- Profiling: identify performance bottlenecks (which function is slow?)

---

### Advanced Cancellation Semantics (Structured Concurrency, `TaskGroup`)

**What it is**:

- `TaskGroup` (Python 3.11+) = safer task management
- Automatically cancels child tasks if parent cancels
- Better error handling than `gather`

**Prerequisites**:

- Python 3.11+ (api-observatory uses 3.14, so you have it)
- Comfortable with `asyncio.gather`

---

## You Should Be Able To

By end of Pillar 1, you should be able to:

✅ Write fully type-hinted Python code (with generics, unions, `Annotated`)
✅ Create FastAPI app with routes, dependencies, exception handlers
✅ Use Pydantic for request/response validation
✅ Write async functions with `asyncio.gather`, `Semaphore`
✅ Write integration tests with pytest + AsyncClient
✅ Implement cursor pagination (or defend why offset/limit is fine)
✅ Add rate limiting to protect API
✅ Implement request ID middleware
✅ Explain why N+1 queries are bad
✅ Troubleshoot "too many connections" errors

---

## References

- [Python Type Hints](https://peps.python.org/pep-0484/) (PEP 484)
- [FastAPI Official Docs](https://fastapi.tiangolo.com/)
- [Pydantic v2 Docs](https://docs.pydantic.dev/latest/)
- [asyncio Docs](https://docs.python.org/3/library/asyncio.html)
- [pytest Docs](https://docs.pytest.org/)

---

## Checklist — Pillar 1: Core Backend

### Foundation 🟢

- [ ] Explain Python OOP: classes, inheritance, ABC, `__dunder__` methods
  - [ ] Know the difference between `@classmethod` and `@staticmethod`
  - [ ] Can write an ABC with abstract methods
- [ ] Explain `async def`, `await`, and when NOT to use async
  - [ ] Know that async is for I/O, not CPU-bound work
  - [ ] Can write a simple `asyncio.gather` call
- [ ] Build a FastAPI route with Pydantic request + response schemas
  - [ ] Know how `HTTPException` works and what status codes to use
- [ ] Write a pytest test with a fixture
  - [ ] Know `asyncio_mode = "auto"` removes `@pytest.mark.asyncio`

### Middle 🟡

- [ ] Explain Pydantic v2: `model_config`, `field_validator`, `model_validator`
  - [ ] Know the difference between `mode="before"` and `mode="after"` validators
  - [ ] Can write a validator that checks one field against another
- [ ] Use `Annotated[T, Depends(...)]` DI pattern (not bare `Depends()`)
  - [ ] Explain why bare `Depends()` fails Ruff E275
- [ ] Implement lifespan context manager (startup/shutdown tasks)
- [ ] Write `httpx.AsyncClient` integration test with `ASGITransport`
- [ ] Explain `asyncio.TaskGroup` vs `asyncio.gather` error semantics
  - [ ] Know that `TaskGroup` cancels all on first failure; `gather` depends on `return_exceptions`

### Senior 🔴

- [ ] Explain the event loop: selectors, `run_until_complete`, `run_in_executor`
  - [ ] Know what blocks the event loop (sync I/O, `time.sleep`, CPU work)
  - [ ] Know how to offload blocking code to a thread pool
- [ ] Use `asyncio.Semaphore` to cap concurrency on a hot path
- [ ] Explain `asyncio.shield` and when it prevents unwanted cancellation
- [ ] Design a middleware that propagates correlation IDs to all log calls
- [ ] Explain `expire_on_commit=False` and the `MissingGreenlet` error

### Pre-Interview Refresh ✏️

- [ ] Explain `await` in one sentence
- [ ] `asyncio.gather` vs `asyncio.create_task` — what is the difference?
- [ ] What is the `expire_on_commit=False` gotcha in async SQLAlchemy?
- [ ] Why use `Annotated[T, Depends()]` instead of bare `Depends()`?
- [ ] `async def` vs `def` in FastAPI — when does FastAPI run them in a threadpool?
- [ ] Explain Python's GIL and why it matters (or doesn't) for async code
