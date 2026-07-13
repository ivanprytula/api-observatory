# Observability Guide

Track: B — Engineering Execution

How to instrument, access, and debug observability signals in this project.

---

## Stack Overview

| Tool            | Purpose                                  | Local URL                    |
| --------------- | ---------------------------------------- | ---------------------------- |
| Prometheus      | Metrics collection and storage           | `http://127.0.0.1:9090`      |
| Grafana         | Metrics dashboards and alerting          | `http://127.0.0.1:3000`      |
| Jaeger          | Distributed tracing UI                   | `http://127.0.0.1:16686`     |
| Alertmanager    | Alert routing and silencing              | `http://127.0.0.1:9093`      |
| Sentry          | Exception tracking and error aggregation | external (configure DSN)     |
| Loki            | Log aggregation (Grafana-native)         | `http://127.0.0.1:3100`      |
| OPS Dashboard   | Live SSE-based operational status        | `http://127.0.0.1:8003/admin` |

All tools start with `docker compose up` or `just up`.

---

## Metrics (Prometheus)

### Endpoint

The ingestor service exposes metrics at `GET /metrics` (plain text, Prometheus format 0.0.4).

Prometheus is configured at `infra/monitoring/prometheus.yml` and scrapes ingestor by default.

### Custom application metrics

All custom metrics live in `services/ingestor/metrics.py`.

| Metric                                    | Type      | Labels                            | Meaning                                       |
| ----------------------------------------- | --------- | --------------------------------- | --------------------------------------------- |
| `pipeline_observations_created_total`          | Counter   | `endpoint`                        | Successful observation INSERTs per endpoint        |
| `pipeline_observations_upsert_conflicts_total` | Counter   | `mode`                            | Upsert conflicts resolved (idempotent/strict) |
| `pipeline_llm_prompt_tokens_total`        | Counter   | `model`, `endpoint`               | LLM prompt tokens consumed                   |
| `pipeline_circuit_breaker_state`          | Gauge     | `circuit`                         | 0=CLOSED, 1=OPEN, 2=HALF_OPEN                |
| `pipeline_batch_insert_size`              | Histogram | —                                 | Distribution of batch sizes per /batch call   |
| `pipeline_enrich_duration_seconds`        | Histogram | —                                 | Wall time for /enrich fan-out calls           |
| `pipeline_cache_hits_total`               | Counter   | `operation`                       | Cache hits in the observation cache                |
| `pipeline_cache_misses_total`             | Counter   | `operation`                       | Cache misses (fetch from DB instead)          |
| `pipeline_cache_errors_total`             | Counter   | `operation`                       | Cache errors (fail-open, logged as warning)   |
| `pipeline_job_executions_total`           | Counter   | `job_name`, `status`              | Scheduled job completions by outcome          |
| `pipeline_job_duration_seconds`           | Histogram | `job_name`                        | Scheduled job wall-clock execution time       |
| `pipeline_background_jobs_submitted_total`| Counter   | `kind`                            | Background jobs enqueued                      |
| `pipeline_background_jobs_processed_total`| Counter   | `kind`, `status`                  | Background jobs processed by outcome          |
| `pipeline_background_jobs_in_queue`       | Gauge     | —                                 | Jobs currently waiting in queue               |
| `pipeline_background_jobs_active`         | Gauge     | —                                 | Jobs currently being processed                |

FastAPI HTTP metrics (from `prometheus-fastapi-instrumentator`) are also exposed:
`http_requests_total`, `http_request_duration_seconds_bucket`, `http_request_size_bytes`, `http_response_size_bytes`.

### Useful Prometheus queries

```promql
# Request rate (5m window)
rate(http_requests_total[5m])

# Error rate (4xx + 5xx)
rate(http_requests_total{status=~"4..|5.."}[5m])

# P95 latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Circuit breaker is open
pipeline_circuit_breaker_state == 1

# Cache hit ratio
rate(pipeline_cache_hits_total[5m])
  / (rate(pipeline_cache_hits_total[5m]) + rate(pipeline_cache_misses_total[5m]))

# Background queue depth
pipeline_background_jobs_in_queue

# Scheduled job failure rate
rate(pipeline_job_executions_total{status="failed"}[10m])
```

### Alert rules

Rules live in `infra/monitoring/rules/`. Alertmanager config is in `infra/monitoring/alertmanager.yml`.

Current SLO-focused alerts cover:

- `/health` p95 latency
- `/readyz` p95 latency
- `/readyz` 5xx failure rate
- background job queue lag via `pipeline_background_jobs_in_queue`

Validate rules locally with:

```bash
docker run --rm -v "$PWD/infra/monitoring:/etc/prometheus" prom/prometheus:v2.54.1 promtool check config /etc/prometheus/prometheus.yml
docker run --rm -v "$PWD/infra/monitoring:/etc/prometheus" prom/prometheus:v2.54.1 promtool check rules /etc/prometheus/rules/alert.rules.yml
```

### Smoke deploy check

Use the prod-like compose overlay to verify the stack boots under tighter resource constraints and responds on both probe endpoints:

```bash
just smoke-deploy
```

---

## Tracing (Jaeger + OpenTelemetry)

### How it works

The processor service and ingestor service export traces via OTLP to Jaeger.

- OTel endpoint (gRPC): `http://jaeger:4317`
- OTel endpoint (HTTP): `http://jaeger:4318`
- Jaeger UI: `http://127.0.0.1:16686`

Tracing is enabled when `OTEL_ENABLED=true`. See `services/processor/otel.py` for the initialisation pattern.

### Trace ID propagation

The processor service propagates a `trace_id` via `ContextVar` across async consumer boundaries so that all log observations emitted during a single Kafka message processing carry the same trace ID. This allows correlating Jaeger traces with structured log lines.

### Searching traces

1. Open Jaeger UI at `http://127.0.0.1:16686`.
2. Select service (e.g., `ingestor` or `processor`).
3. Filter by operation name, duration, or tags.
4. Click a trace to see the span waterfall.

---

## Structured Logging

### Format

All services emit JSON logs to stdout. Log observations are collected by Loki (via Docker log driver or Promtail) and queryable in Grafana.

Standard fields on every log line:

| Field       | Description                                             |
| ----------- | ------------------------------------------------------- |
| `timestamp` | ISO 8601 UTC                                            |
| `level`     | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`         |
| `event`     | Short snake_case event name (e.g., `observation_created`)    |
| `cid`       | Correlation / request ID (propagated from `X-CID` header or generated) |
| `service`   | Service name                                            |

Additional context fields are added per event (e.g., `observation_id`, `source`, `tenant_id`).

### Correlation ID

The ingestor propagates a CID (correlation ID) through the entire request lifecycle. Include the `X-CID` header on API calls to trace a request end-to-end across logs.

### Querying logs in Grafana (Loki)

```logql
# All errors in ingestor
{container="data-pipeline-ingestor"} | json | level="ERROR"

# Trace a specific request
{container="data-pipeline-ingestor"} | json | cid="your-cid-here"

# Circuit breaker opens
{container="data-pipeline-ingestor"} | json | event="circuit_opened"
```

---

## Exception Tracking (Sentry)

Sentry is optional and disabled unless `SENTRY_ENABLED=true` and `SENTRY_DSN` are set.

Configure in `.env`:

```bash
SENTRY_ENABLED=true
SENTRY_DSN=https://your-key@sentry.io/your-project
```

Enabled integrations: FastAPI, SQLAlchemy, aiohttp, logging.

Production recommendation: set `SENTRY_TRACES_SAMPLE_RATE=0.1` to avoid excessive trace volume.

---

## OPS Dashboard (Live Operational View)

The dashboard service exposes a live admin UI at `http://127.0.0.1:8003/admin` built with HTMX + Jinja2 + Server-Sent Events.

Key panels:

| Panel            | URL                                         | Refreshes via |
| ---------------- | ------------------------------------------- | ------------- |
| Worker health    | `GET /partials/admin/workers/health`        | HTMX polling  |
| Task lookup      | `GET /partials/admin/tasks?id=<task_id>`    | On demand     |
| Manual rerun     | `POST /partials/admin/rerun`                | On submit     |
| Session bootstrap| `POST /partials/admin/session`              | On submit     |

This gives operational visibility without requiring CLI access.

---

## Debug Workflows

### Investigate a failed observation ingestion

1. Find the correlation ID in the response body or the API log line (`cid` field).
2. In Grafana (Loki), query `{container="data-pipeline-ingestor"} | json | cid="<cid>"`.
3. Check whether the circuit breaker is open: `pipeline_circuit_breaker_state == 1` in Prometheus.
4. If the error originated in the processor, find the matching trace in Jaeger using the trace ID from the processor logs.
5. If an exception was raised, check Sentry for the full stack trace and context.

### Investigate a slow endpoint

1. In Prometheus, run `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))`.
2. Identify which route has elevated P95. Filter by `handler` label.
3. Open Jaeger and search for long traces on that operation.
4. Check `pipeline_enrich_duration_seconds` if the slow path goes through `/enrich`.
5. Check `pipeline_cache_misses_total` — a spike here means cache is cold or Cache is down.

### Investigate background queue buildup

1. Watch `pipeline_background_jobs_in_queue` in Prometheus or Grafana.
2. Check `pipeline_background_jobs_active` — if it is 0 while queue is non-zero, workers are stalled.
3. Look for worker error logs: `{container="data-pipeline-ingestor"} | json | event="worker_error"`.

---

## Adding a New Metric

1. Define the metric in `services/ingestor/metrics.py` following the `<namespace>_<subsystem>_<unit>_<suffix>` naming convention.
2. Add the `inc()` / `observe()` / `set()` call at the relevant code site.
3. Import the module at startup so the metric is registered (see existing imports in `main.py`).
4. Update this file and the Grafana dashboard JSON in `infra/monitoring/grafana/`.

---

## Related

- Architecture Overview — service boundaries and deployment
- Pillar 4 Observability — observability learning reference and code examples
- [docker-compose.yml](../../docker-compose.yml) — all service ports and OTEL env vars
