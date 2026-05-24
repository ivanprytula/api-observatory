---
description: "Use when writing, editing, or reviewing tests in this project. Covers the aiosqlite fixture setup, asyncio_mode=auto rules, client/db fixture patterns, dependency_overrides, and test structure conventions."
applyTo: "tests/**/*.py"
---

# Test Conventions

## Test Runner Setup

- `asyncio_mode = "auto"` is set in `pyproject.toml` — **do NOT add `@pytest.mark.asyncio`** to any test function or fixture (it is redundant and causes warnings)
- Tests use `aiosqlite` in-memory SQLite — no real PostgreSQL needed for single-process runs

### Parallel testing note

- The default in-memory SQLite backend is not safe for `pytest-xdist` parallel runs (`-n auto`).
    If you need parallel test execution, set `DATABASE_URL_TEST` to a PostgreSQL instance and
    run the tests against that database (the test `conftest.py` will automatically use `NullPool`
    for PostgreSQL to avoid cross-event-loop connection sharing).

## Fixtures (defined in `conftest.py`)

Two fixtures are available. Always prefer `client` for API tests:

| Fixture | Type | Use for |
|---------|------|---------|
| `db` | `AsyncSession` | Direct CRUD function tests |
| `client` | `httpx.AsyncClient` | API endpoint tests (most tests) |

**How they work:**
- `db` creates the full schema (`create_all`), yields a session, then tears down (`drop_all`) — each test gets a clean database
- `client` wraps `db` via `app.dependency_overrides[get_db]` and clears overrides on teardown
- Use `@pytest_asyncio.fixture()` for any new async fixtures — not `@pytest.fixture()`

## Adding a New Fixture

```python
# CORRECT
@pytest_asyncio.fixture()
async def processed_record(client: AsyncClient) -> dict:
    r = await client.post("/api/v1/records", json=_RECORD)
    await client.patch(f"/api/v1/records/{r.json()['id']}/process")
    return r.json()

# WRONG — sync fixture for async setup
@pytest.fixture()
def processed_record(client):
    ...
```

## Test Structure

Group tests by endpoint in clearly labelled sections (match the existing `# ---` comment style).

Every endpoint needs three test types:
1. **Happy path** — correct status code and response shape
2. **Not found (404)** — use a non-existent ID like `99999`
3. **Validation (422)** — missing required field, out-of-range value, or constraint violation

```python
_RECORD = {
    "source": "api.example.com",
    "timestamp": "2024-01-15T10:00:00",
    "data": {"price": 123.45},
    "tags": ["Stock", "NASDAQ"],
}

async def test_create_record(client: AsyncClient) -> None:
    r = await client.post("/api/v1/records", json=_RECORD)
    assert r.status_code == 201
    assert r.json()["source"] == "api.example.com"

async def test_create_record_missing_source(client: AsyncClient) -> None:
    bad = {**_RECORD}
    del bad["source"]
    r = await client.post("/api/v1/records", json=bad)
    assert r.status_code == 422
```

## Key Gotchas

- **Shared in-memory engine**: All tests share the same `_engine` instance in `conftest.py`. Schema is created/dropped per `db` fixture invocation — tests are isolated but sequential, not parallel.
- **`expire_on_commit=False`** is set on `_AsyncSessionLocal` in `conftest.py`. New session makers you add must include this — otherwise attribute access after `commit()` raises `MissingGreenlet`.
- **SQLite dialect**: Avoid PostgreSQL-specific assertions (e.g. checking for `RETURNING` clause behaviour, `ON CONFLICT` semantics). The CRUD layer deliberately avoids these.
- **Tag normalization**: Tags are lowercased by `RecordRequest.lowercase_tags` validator — assert `["stock", "nasdaq"]`, not `["Stock", "NASDAQ"]`.
