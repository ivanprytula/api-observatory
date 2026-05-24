---
description: "Use when writing, adding, or reviewing FastAPI integration tests. Covers AsyncClient setup, ASGITransport, dependency_overrides pattern, response shape assertions, and test data conventions for this project's httpx + aiosqlite test stack."
applyTo: "tests/**/*.py"
---

# FastAPI Testing Conventions

## Client Setup — `AsyncClient` + `ASGITransport`

Never use `TestClient` (sync). Always use `httpx.AsyncClient` with `ASGITransport`:

```python
from httpx import ASGITransport, AsyncClient
from app.main import app

async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
    yield ac
```

The `base_url="http://test"` is required — httpx needs a valid base URL even for in-process transport.

## Dependency Override — Injecting the Test DB

Override `get_db` with a function that yields the test session. Always clear overrides in teardown:

```python
from app.database import get_db

async def _override() -> AsyncSession:
    yield db  # db is the pytest_asyncio fixture session

app.dependency_overrides[get_db] = _override
# ... run test ...
app.dependency_overrides.clear()  # MUST clear — shared app state between tests
```

The `client` fixture in `conftest.py` handles this automatically. Use `client` for all API tests — only use `db` directly when testing CRUD functions in isolation.

## Test Function Signatures

All test functions must be `async def` with an explicit return type of `None`:

```python
# CORRECT
async def test_create_record(client: AsyncClient) -> None:
    r = await client.post("/api/v1/records", json=_RECORD)
    assert r.status_code == 201

# WRONG — sync, missing return type
def test_create_record(client):
    ...
```

Do **not** add `@pytest.mark.asyncio` — `asyncio_mode = "auto"` in `pyproject.toml` handles this.

## Test Data — Module-Level Constants

Define shared request payloads as module-level constants. Use `{**_RECORD, "field": new_value}` to produce variants:

```python
_RECORD = {
    "source": "api.example.com",
    "timestamp": "2024-01-15T10:00:00",
    "data": {"price": 123.45},
    "tags": ["Stock", "NASDAQ"],
}

# Variant — only override what differs
r = await client.post("/api/v1/records", json={**_RECORD, "source": "other.com"})
```

Always use a past timestamp (well before today's date) — the `not_in_future` validator rejects future timestamps with 422.

## Response Assertion Pattern

Check both the status code and the response shape. Never assert only the status code:

```python
# CORRECT
r = await client.post("/api/v1/records", json=_RECORD)
assert r.status_code == 201
body = r.json()
assert body["source"] == "api.example.com"
assert body["tags"] == ["stock", "nasdaq"]   # lowercased by validator
assert body["id"] is not None
assert body["processed"] is False

# INCOMPLETE — status only, no shape check
assert r.status_code == 201
```

Use `is True` / `is False` for boolean fields — not `== True` / `== False`.

## Tag Normalization

Tags are always lowercased by `RecordRequest.lowercase_tags`. Assert the normalized form:

```python
# CORRECT — assert downstream value, not what was sent
assert body["tags"] == ["stock", "nasdaq"]

# WRONG — asserts the input, not what the API returns
assert body["tags"] == ["Stock", "NASDAQ"]
```

## Pagination Response Shape

List endpoints return a `{ "records": [...], "pagination": {...} }` envelope. Assert both levels:

```python
r = await client.get("/api/v1/records")
body = r.json()
assert body["records"] == []
assert body["pagination"]["total"] == 0
assert body["pagination"]["has_more"] is False
```

For pagination tests, seed data then assert `has_more`, `total`, and the slice length separately — don't rely on ordering unless explicitly tested:

```python
for i in range(5):
    await client.post("/api/v1/records", json={**_RECORD, "source": f"src-{i}"})
r = await client.get("/api/v1/records?skip=0&limit=3")
body = r.json()
assert len(body["records"]) == 3
assert body["pagination"]["total"] == 5
assert body["pagination"]["has_more"] is True
```

## The Three-Test Rule per Endpoint

Every route needs at minimum:

| Test | Status Code | Pattern |
|------|------------|---------|
| Happy path | 2xx | full shape assertion |
| Not found | 404 | use non-existent ID `99999` |
| Validation error | 422 | missing field, bad value, or violated constraint |

```python
# 404 pattern
async def test_get_nonexistent_record(client: AsyncClient) -> None:
    r = await client.get("/api/v1/records/99999")
    assert r.status_code == 404

# 422 pattern — missing required field
async def test_create_record_missing_source(client: AsyncClient) -> None:
    bad = {**_RECORD}
    del bad["source"]
    r = await client.post("/api/v1/records", json=bad)
    assert r.status_code == 422
```

## Section Comments

Group tests by endpoint using the existing `# ---` separator style:

```python
# ---------------------------------------------------------------------------
# Create single record
# ---------------------------------------------------------------------------
async def test_create_record(client: AsyncClient) -> None:
    ...

# ---------------------------------------------------------------------------
# List / pagination
# ---------------------------------------------------------------------------
async def test_list_records_empty(client: AsyncClient) -> None:
    ...
```

## Unused Import Warning

`pytest` must be imported only if `pytest.raises` or `pytest.mark` is used. Remove the import if unused — ruff (rule F401) will flag it:

```python
# Only import what you use
import pytest  # only if using pytest.raises(...) or similar
from httpx import AsyncClient
```
