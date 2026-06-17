# Pillar 3: Reliable Ingestion & Scheduling

Track: C — Architecture and Platform Strategy

## Overview

Pillar 3 implements a production-ready job scheduling framework for reliable, fault-tolerant data ingestion. It provides:

1. **APScheduler-based job execution** — time-based and interval-based scheduling
2. **Exponential backoff with jitter** — retries with thundering herd prevention
3. **Idempotency tracking** — deduplication for single-instance deployments
4. **Health metrics & observability** — success rates, error tracking, execution times
5. **Graceful lifecycle management** — startup/shutdown, job cancellation handling

## Architecture

### Module Organization

```text
ingestor/core/
├── job_types.py          # Job and JobHealthMetrics dataclasses
├── handlers.py           # Handler wrapping (session injection, timeouts, metrics)
├── scheduler.py          # JobScheduler class (APScheduler wrapper)
├── retry.py              # Exponential backoff decorator, idempotency tracking
└── ...

ingestor/
├── jobs.py               # Ingestion job implementations
├── jobs_registry.py      # Centralized job registration
├── services_lifecycle.py # External service initialization/cleanup
└── main.py               # FastAPI app with lifespan (uses all above)
```

### Design Principles

**Separation of Concerns**:

- `job_types.py`: Data models (no logic)
- `handlers.py`: Execution logic (timeout, metrics, session injection)
- `scheduler.py`: Scheduling orchestration (APScheduler wrapper)
- `retry.py`: Retry policy and idempotency (reuses `rate_limiting_advanced.apply_jitter()`)
- `jobs_registry.py`: Job registration (centralized, extensible)
- `services_lifecycle.py`: External service management (fail-open pattern)

**Non-blocking Extensibility**: To add a new scheduled job:

1. Implement the async handler in `ingestor/jobs.py`
2. Register it in `register_jobs()` in `ingestor/jobs_registry.py`
3. No changes needed to `main.py` (called via `jobs_registry.register_jobs()`)

**Stateless Job Handlers**: Jobs receive `AsyncSession` as a parameter (dependency injection pattern), enabling:

- Easy testing (mock the session)
- No global state (testable, stateless)
- Future migration to Celery/arq (handler interface unchanged)

## Job Lifecycle

### 1. Registration

```python
# In ingestor/jobs_registry.py

@scheduler.job(
    name="ingest_hourly_data",
    trigger=IntervalTrigger(hours=1),  # Run every hour
    max_retries=3,                      # Retry 3 times on failure
    timeout_seconds=300,                # Timeout after 5 minutes
    tags={"batch", "critical"},         # Metadata tags
)
async def ingest_hourly(db: AsyncSession) -> dict[str, Any]:
    """Fetch and ingest data every hour."""
    # Implementation...
    return {"inserted": 100}
```

### 2. Execution (with Wrapping)

When a job runs, `wrap_job_handler()` applies:

```text
wrap_job_handler()
├── Create AsyncSession from factory
├── Execute handler with timeout
│   └── await asyncio.wait_for(handler(session), timeout=300)
├── Update health metrics on success
│   ├── success_count += 1
│   ├── last_run_at = now()
│   └── last_error = None
└── Update health metrics on failure
    ├── failure_count += 1
    ├── last_run_at = now()
    └── last_error = exception_message
```

### 3. Health Tracking

Every job has a `JobHealthMetrics` instance:

```python
job.health.success_rate  # [0.0, 1.0]
job.health.is_healthy    # success_rate >= 80% AND last_error is None
job.health.last_run_at   # datetime of last execution
job.health.failure_count # Total failures (cumulative)
```

Available via health check endpoints:

```bash
# All jobs' health
curl http://127.0.0.1:8000/health/jobs-metrics

# Specific job's health
curl http://127.0.0.1:8000/health/jobs/ingest_hourly_data-metrics
```

## Retry & Backoff Strategy

### Exponential Backoff with Jitter

Implemented via `@exponential_backoff()` decorator in `ingestor/core/retry.py`:

```python
@exponential_backoff(
    max_retries=3,
    base_delay=1.0,
    max_delay=60.0,
    jitter=True,  # Prevents thundering herd
)
async def ingest_scheduled_batch_example(db: AsyncSession) -> dict[str, Any]:
    # Implementation
```

**Backoff formula**:

```text
delay = min(base_delay * (2 ** attempt), max_delay)
```

**With jitter** (±20% variance):

```text
final_delay = apply_jitter(delay, -delay*0.2, +delay*0.2)
```

**Why jitter?** Prevents many clients from retrying simultaneously (thundering herd problem). Spreads retries across a time window.

### Idempotency Tracking

For single-instance deployments, use `IdempotencyKeyTracker`:

```python
from ingestor.core.retry import IdempotencyKeyTracker

tracker = IdempotencyKeyTracker(ttl_seconds=3600)

if tracker.is_duplicate("batch_2024_04_22"):
    logger.info("Duplicate batch skipped")
    return

# Process batch...
tracker.mark_seen("batch_2024_04_22")
```

**For distributed deployments**: Use database unique constraints or Cache-backed dedup (Pillar 2).

## Configuration

### Environment Variables

| Variable              | Default | Notes                                              |
| --------------------- | ------- | -------------------------------------------------- |
| `JOB_TIMEOUT_SECONDS` | `300`   | Default timeout for all jobs (overridable per-job) |
| `MAX_RETRIES`         | `3`     | Default max retries (overridable per-job)          |

Note: scheduler lifecycle is controlled by app startup/lifespan wiring; there is currently no standalone `SCHEDULER_ENABLED` setting in `ingestor/config.py`.

### Example: Enable a Scheduled Job

By default, jobs have `trigger=None` (disabled). To enable:

```python
# In jobs_registry.py
@scheduler.job(
    name="ingest_batch_daily",
    trigger=CronTrigger(hour=0, minute=0),  # Run at midnight UTC
    max_retries=3,
    timeout_seconds=600,
)
async def daily_ingest(db: AsyncSession) -> dict[str, Any]:
    # Implementation
```

## Testing

### Unit Tests

Test job handlers without scheduler overhead:

```python
async def test_ingest_single():
    mock_db = AsyncMock(spec=AsyncSession)
    request = RecordRequest(...)

    result = await ingest_api_single(mock_db, request)
    assert result is not None
```

### Integration Tests

Test scheduler lifecycle:

```python
async def test_scheduler_lifecycle():
    scheduler = JobScheduler()

    @scheduler.job(name="test", trigger=IntervalTrigger(hours=1))
    async def handler(db: AsyncSession) -> dict:
        return {}

    await scheduler.start(session_factory)
    assert scheduler._scheduler.running

    await scheduler.stop()
    assert not scheduler._scheduler.running
```

### Run Tests

```bash
# Run all scheduler tests
uv run pytest tests/integration/test_scheduler.py -v

# Run specific test class
uv run pytest tests/integration/test_scheduler.py::TestJobScheduler -v

# Run with coverage
uv run pytest tests/integration/test_scheduler.py --cov=ingestor.core
```

## Operational Runbook

### Response Format
<!-- Dev server startup is covered in the Commands Reference -->

```json
{
  "scheduler_running": true,
  "job_count": 2,
  "jobs": {
    "ingest_scheduled_batch_example": {
      "last_run_at": "2024-04-22T10:15:30",
      "success_count": 45,
      "failure_count": 2,
      "success_rate": 0.957,
      "is_healthy": true,
      "last_error": null,
      "next_run_time": "2024-04-22T11:15:30"
    }
  }
}
```

### Monitoring

**Success rate tracking**:

- Green (healthy): ≥80% success rate AND no recent errors
- Yellow (degraded): <80% success rate
- Red (unhealthy): Any recent errors

**Alert conditions**:

- Success rate drops below 80%
- Job hasn't run in 2× expected interval
- Job timeout occurs 3 times in a row

### Debugging Failed Jobs

Check specific job health at `GET /health/jobs/{job_name}-metrics`,
view logs with `docker-compose logs ingestor`,
and list registered jobs at `GET /health/jobs-metrics`.

## Future Work (Phases 2+)

### Phase 2: Distributed Scaling

- Replace APScheduler with Celery + Cache
- Move job state to Cache instead of in-memory
- Add worker pool configuration
- Enable horizontal scaling (multiple worker instances)

### Phase 3: Advanced DAG/ETL

- Migration path: Airflow for complex DAGs
- Job dependencies and conditional logic
- Data lineage tracking

### Phase 4: Enhanced Observability

- OpenTelemetry tracing for job execution
- Custom metrics (job duration percentiles, queue depth)
- Alert integrations (PagerDuty, Slack)

## Troubleshooting

### Jobs Not Running

1. **Check scheduler is started**: `curl http://127.0.0.1:8000/health/jobs-metrics`
   If `"scheduler_running": false`, scheduler failed to start.

2. **Check job registration**: `curl http://127.0.0.1:8000/health/jobs-metrics | jq '.jobs | keys'`

3. **Check logs for startup errors**: `docker-compose logs ingestor | grep "scheduler_startup"`

4. **Check job trigger is not `None`**:

   ```python
   # In jobs_registry.py, ensure trigger is set
   trigger=IntervalTrigger(hours=1)  # Not trigger=None
   ```

### Job Always Times Out

1. Increase `timeout_seconds` in job definition
2. Profile the job handler to find bottleneck (slow DB query, external API)
3. Check database connection pool size

### Job Fails with "Session Not Found"

Ensure handler receives `db: AsyncSession` as parameter (dependency injection):

```python
# CORRECT
async def handler(db: AsyncSession) -> dict:
    return await crud.get_records(db)

# WRONG (global state anti-pattern)
async def handler() -> dict:
    db = get_db()  # ❌ Not injected
```

---

## References

- [APScheduler Documentation](https://apscheduler.readthedocs.io/)
- [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/#lifespan)
- [Exponential Backoff & Jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)
