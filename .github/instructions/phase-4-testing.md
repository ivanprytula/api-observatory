# Phase 5 — Comprehensive Testing & Observability

**Duration**: 2 weeks
**Goal**: pytest fixtures for async/Celery/Qdrant, chaos testing, load testing, structured logging
**Success Metric**: 100% test coverage, <5min test suite, chaos tests passing (Qdrant down, API timeout)

---

## Core Learning Objective

Master async testing (fixtures, mocking), dependency injection, test data factories, and chaos engineering patterns.

---

## Interview Questions

### Core Q: "Design Test Suite for Async FastAPI + Qdrant + Celery"

**Expected Answer:**

- Fixture layers: async_db_session (SQLite in-mem), mocked_qdrant (mock responses), mocked_celery (apply_async → immediate)
- Parametrization: test multiple inputs (3 sources, 5 price ranges, etc.)
- Async context: pytest-asyncio with event_loop fixture, not decorators (cleaner)
- Dependency overrides: FastAPI dependency_overrides pattern to inject mocks
- Database transactions: Rollback after each test (isolation)
- Factories: Use Faker + SQLAlchemy ORM to generate test data (beats hardcoded dicts)

**Talking Points:**

- Fixture scope: function (isolated, slower) vs session (shared, faster but state leaks)
- Mock vs real: Mock external APIs (OpenAI, Qdrant), use real DB (SQLite in-mem)
- Parametrization vs loops: `@pytest.mark.parametrize` generates separate test runs (better reports)
- Test doubles: stub (no-op), mock (assert called), spy (record calls)

---

### Follow-Up: "Celery Task Test Without Real Queue?"

**Expected Answer:**

- Method 1: `celery.current_app.conf.task_always_eager = True` (execute immediately, no queue)
- Method 2: `@patch('module.celery_app.task.apply_async')` + side_effect (mock to track calls)
- Method 3: Dependency override + inject mock Celery app
- Preferred: Method 1 (simple) or Method 3 (integrates with FastAPI dependencies)

**Talking Points:**

- Task state: success, failed, retry. Test retry logic (exponential backoff).
- Result backend: Don't mock unless testing result storage. Focus on task logic.
- Idempotency: Tasks should be idempotent (safe to re-run). Test with duplicate calls.

---

### Follow-Up: "Test Flakiness: Same Test Passes/Fails Randomly"

**Expected Answer:**

- Suspect timing: `asyncio.sleep()` without mocking, async race conditions, race on database commit
- Suspect shared state: Test modifies global or session state without cleanup
- Suspect resource contention: Port conflicts, temp file cleanup, database locks
- Fix: (1) Mock time (freezegun), (2) Fixture cleanup (auto-cleanup after test), (3) Use random ports

**Talking Points:**

- CI flakiness higher than local (due to resource contention, slower machines)
- Retry on CI: pytest-repeat plugin to auto-retry flaky tests 3×
- Identify via: Run test 100× locally (`pytest --count=100`), if >99% pass, flaky

---

## Real life production example — Production-Ready

### Architecture

```text
Client → FastAPI → Qdrant (vector search) + PostgreSQL (metadata) + Celery (background tasks)
```

```text
conftest.py (shared fixtures)
  ├─► event_loop: asyncio loop for all tests
  ├─► async_db_session: SQLite in-mem, rollback after each test
  ├─► client: AsyncClient with dependency_overrides
  ├─► mocked_qdrant: Mock QdrantService (return test vectors)
  ├─► mocked_celery: Celery eager mode (no queue)
  └─► faker: Generate test data

tests/
  ├─► unit/test_embeddings.py: Embedding logic (mock OpenAI)
  ├─► unit/test_scrapers.py: Scraper logic (mock HttpX)
  ├─► integration/test_search_e2e.py: End-to-end (Qdrant + DB)
  ├─► chaos/test_failures.py: Qdrant down, API timeout
  └─► load/test_performance.py: k6 load test
```

### Implementation Checklist

- [ ] **tests/conftest.py** — Shared fixtures

  ```python
  import pytest
  from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
  from fastapi.testclient import TestClient
  from httpx import AsyncClient
  from faker import Faker
  from unittest.mock import AsyncMock, patch

  @pytest.fixture
  async def async_db_session():
      """SQLite in-mem session, rollback after test."""
      engine = create_async_engine('sqlite+aiosqlite:///:memory:')
      async with engine.begin() as conn:
          await conn.run_sync(Base.metadata.create_all)

      async_session = AsyncSessionLocal(bind=engine)
      yield async_session
      await async_session.rollback()
      await engine.dispose()

  @pytest.fixture
  def client(async_db_session):
      """FastAPI test client with dependency overrides."""
      app.dependency_overrides[get_db] = lambda: async_db_session
      return AsyncClient(app=app)

  @pytest.fixture
  def mocked_qdrant():
      """Mock QdrantService."""
      with patch('app.qdrant_client.QdrantService') as mock:
          mock.return_value.search = AsyncMock(return_value=[
              {'score': 0.95, 'source': 'test', 'price': 100.0, 'description': 'test desc'}
          ])
          yield mock

  @pytest.fixture
  def mocked_celery():
      """Celery eager mode (no queue)."""
      with patch.dict('celery.current_app.conf', task_always_eager=True):
          yield

  @pytest.fixture
  def faker():
      return Faker()
  ```

- [ ] **tests/unit/test_embeddings.py** — Embeddings logic

  ```python
  import pytest
  from app.embeddings import embed_text, embed_batch
  from unittest.mock import patch, AsyncMock

  @pytest.mark.asyncio
  async def test_embed_text_cached():
      """Embedding cached on second call."""
      with patch('openai.Embedding.create') as mock_api:
          mock_api.return_value = {
              'data': [{'embedding': [0.1, 0.2, 0.3]}]
          }

          # First call
          result1 = embed_text("hello")
          assert mock_api.call_count == 1

          # Second call (cached)
          result2 = embed_text("hello")
          assert result1 == result2
          assert mock_api.call_count == 1  # No new API call

  @pytest.mark.asyncio
  async def test_embed_batch():
      """Batch embedding efficient."""
      texts = ["hello", "world", "test"]
      with patch('openai.AsyncOpenAI.embeddings.create') as mock_api:
          mock_api.return_value = AsyncMock()
          mock_api.return_value.__aiter__ = lambda self: async_iter([...])

          results = await embed_batch(texts)
          assert len(results) == 3
          # Assert API called once, not three times
          assert mock_api.call_count == 1
  ```

- [ ] **tests/integration/test_search_e2e.py** — End-to-end

  ```python
  import pytest
  from httpx import AsyncClient

  @pytest.mark.asyncio
  async def test_search_end_to_end(client, async_db_session, mocked_qdrant):
      """Full pipeline: create record → embed → search."""
      # Create record
      resp = await client.post('/api/v1/records', json={
          'value': 100.0,
          'source_id': 'test_source'
      })
      assert resp.status_code == 201

      # Search
      resp = await client.post('/api/v1/search', json={
          'query': 'cheap items'
      })
      assert resp.status_code == 200
      results = resp.json()
      assert len(results) > 0
      assert results[0]['score'] > 0.8
  ```

- [ ] **tests/chaos/test_failures.py** — Chaos testing

  ```python
  import pytest
  from unittest.mock import patch, AsyncMock
  from httpx import ConnectError

  @pytest.mark.asyncio
  async def test_qdrant_down(client):
      """Search fails gracefully when Qdrant down."""
      with patch('app.qdrant_client.QdrantService.search') as mock:
          mock.side_effect = ConnectionError("Qdrant unreachable")

          with pytest.raises(HTTPException) as exc:
              await client.post('/api/v1/search', json={'query': 'test'})

          assert exc.value.status_code == 503  # Service Unavailable

  @pytest.mark.asyncio
  async def test_openai_rate_limited(client):
      """Embeddings retry on 429."""
      with patch('openai.Embedding.create') as mock:
          # First call: 429, Second call: success
          mock.side_effect = [
              Exception("429 Rate Limited"),
              {'data': [{'embedding': [0.1, 0.2]}]}
          ]

          result = await client.post('/api/v1/search', json={'query': 'test'})
          # Should retry and eventually succeed (with exponential backoff)
          assert result.status_code == 200
  ```

- [ ] **tests/load/test_performance.py** — Performance

  ```python
  import pytest
  import time

  @pytest.mark.asyncio
  async def test_search_latency(client):
      """Search p99 latency <200ms."""
      latencies = []
      for _ in range(100):
          start = time.perf_counter()
          await client.post('/api/v1/search', json={'query': 'test'})
          latencies.append(time.perf_counter() - start)

      p99 = sorted(latencies)[99]
      assert p99 < 0.2, f"p99 latency {p99}s exceeds 200ms"
  ```

- [ ] **pytest.ini**

  ```ini
  [pytest]
  asyncio_mode = auto
  testpaths = tests
  addopts = --cov=app --cov-report=html --tb=short -v
  markers =
      unit: Unit tests
      integration: Integration tests
      chaos: Chaos tests
      load: Load/performance tests
  ```

- [ ] **Structured Logging**

  ```python
  import logging
  import json
  from pythonjsonlogger import jsonlogger

  # JSON logging to stdout
  handler = logging.StreamHandler()
  formatter = jsonlogger.JsonFormatter()
  handler.setFormatter(formatter)
  logger.addHandler(handler)

  # Use in code:
  logger.info("search_performed", extra={
      'query': query,
      'results_count': len(results),
      'latency_ms': latency,
      'trace_id': trace_id,
  })
  ```

---

## Weekly Checklist

### Week 1: Fixtures + Unit Tests

- [ ] conftest.py: async_db_session, client, mocked_qdrant, mocked_celery fixtures
- [ ] Unit tests for embeddings (cache, batch)
- [ ] Unit tests for scrapers (rate limit, retry)
- [ ] Parametrization: test 3–5 variants per test (prices, sources, query types)
- [ ] Coverage: aim for 90%+ (measure via pytest-cov)
- [ ] Interview Q: "Design test suite for async FastAPI + Qdrant?" → Answer drafted
- [ ] Commits: 6–8 (fixtures, unit tests, parametrization, coverage)

### Week 2: Integration + Chaos

- [ ] Integration tests: end-to-end (record → embed → search)
- [ ] Chaos tests: Qdrant down, OpenAI 429, database timeout
- [ ] Performance tests: latency <200ms p99
- [ ] Load test: k6 script for concurrent searches
- [ ] Test flakiness: run tests 100× locally, identify flaky tests
- [ ] Structured logging: all significant events logged (search, embed, error)
- [ ] Interview Q: "Test Celery tasks?" → Full answer ready
- [ ] Commits: 5–7 (integration tests, chaos, load tests, logging)
- [ ] Portfolio item + LinkedIn post

---

## Success Metrics

| Metric          | Target   | How to Measure                                   |
| --------------- | -------- | ------------------------------------------------ |
| Test coverage   | 100%     | `pytest --cov=app` → show coverage %             |
| Test suite time | <5 min   | `pytest tests/` → measure elapsed time           |
| Test pass rate  | 100%     | All tests pass on CI                             |
| Flaky tests     | 0        | Run 100×: `pytest --count=100 tests/` → all pass |
| Chaos tests     | All pass | Qdrant down, OpenAI 429, DB timeout scenarios    |
| Latency p99     | <200ms   | Performance test on search endpoint              |
| Commit count    | 11–15    | 1 per test suite / feature                       |

---

## Gotchas + Fixes

### Gotcha 1: "Async Fixture Not Applied"

**Symptom**: Fixture runs, but async code doesn't wait (returns coroutine instead of result).
**Cause**: Missing `async def` or not `await`ing in fixture.
**Fix**: Use `@pytest.fixture` (not `@pytest.mark.asyncio`), mark as `async def`, and `pytest-asyncio` handles it.

### Gotcha 2: "Database Locks After Test"

**Symptom**: Test passes alone, fails when run with others (SQLite contention).
**Cause**: Database transaction not rolled back.
**Fix**: `await async_db_session.rollback()` after yield in fixture. Or use in-memory DB (SQLite `:memory:` isolated per test).

### Gotcha 3: "Mocked Dependency Not Injected"

**Symptom**: Test mocks object, but real object still used (mock ignored).
**Cause**: Dependency override not registered or wrong path.
**Fix**: Verify `app.dependency_overrides[get_db] = lambda: mocked_session`. Check import path matches where function is used.

### Gotcha 4: "Performance Test Flaky (Sometimes Fast, Sometimes Slow)"

**Symptom**: `test_search_latency` fails on CI (p99 > 200ms) but passes locally.
**Cause**: CI slower, background processes taking CPU, no warmup run.
**Fix**: (1) Add warmup run (discard first iteration), (2) Relax threshold on CI (p99 < 400ms)

---

## Cleanup (End of Phase 5)

```bash
pytest tests/ --cov=app --cov-report=html
# Open htmlcov/index.html to review coverage
```

---

## Metrics to Monitor Ongoing

- Test suite duration: Alert if > 10 min (tests slowing down)
- Coverage: Alert if < 95% (regression in testing)
- Flaky test rate: Alert if > 1% of runs fail intermittently
- CI failure rate: Alert if > 5% of commits have test failures

---

## Next Phase

**Phase 6: Database Deep Dive**
Query optimization (EXPLAIN ANALYZE, composite indices), pagination patterns, transaction isolation, connection pooling tuning.

**Reference**: Phase 5 tests stable = ready for Phase 6 database optimization.
