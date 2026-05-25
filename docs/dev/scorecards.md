# Provider Scorecards

Rolling-window reliability metrics for every registered API source. A scorecard
answers: "In the last N days, how reliable was this API?"

## What the scorecard measures

| Field | What it tells you |
|-------|-------------------|
| `uptime_pct` | Percentage of probes that succeeded (`is_success = true`) |
| `p50_latency_ms` | Median end-to-end probe latency |
| `p95_latency_ms` | 95th-percentile latency — the "slow tail" |
| `avg_latency_ms` | Mean latency across all probes in the window |
| `error_count` | Absolute number of failed probes |
| `error_budget_burn_rate` | How fast the provider consumes its SLO error budget |
| `sample_count` | Total probes recorded in the window |

### Error-budget burn rate

```text
error_budget_burn_rate = error_rate / (1 - slo_target_pct / 100)
```

- **1.0** — consuming budget at exactly the allowed pace (on track to exhaust it at the end of the window).
- **< 1.0** — healthy; budget has headroom.
- **> 1.0** — burning faster than allowed; provider will exhaust its SLO budget before the window closes.

## API endpoints

### Record a health probe

```bash
POST /api/v1/scorecards/samples
```

```json
{
  "source_id": 1,
  "sampled_at": "2026-05-25T12:00:00Z",
  "latency_ms": 142.5,
  "is_success": true,
  "http_status": 200,
  "response_body_hash": "a3f5...64-char-sha256-hex...",
  "region": "eu-west-1"
}
```

The probe scheduler calls this automatically for every active `SourceProfile`.
You can also POST manually for synthetic monitoring or replays.

### Get a scorecard for one source

```bash
GET /api/v1/scorecards/{source_id}
GET /api/v1/scorecards/1?days=30&slo_target_pct=99.5
```

#### Query parameters

| Param | Default | Range | Description |
|-------|---------|-------|-------------|
| `days` | `7` | `1–90` | Look-back window |
| `slo_target_pct` | `99.9` | `90–100` | SLO target used for burn-rate calculation |

#### Response example

```json
{
  "source_id": 1,
  "source_name": "httpbin",
  "window_days": 7,
  "sample_count": 168,
  "error_count": 2,
  "uptime_pct": 98.8095,
  "avg_latency_ms": 87.4,
  "p50_latency_ms": 82.1,
  "p95_latency_ms": 213.0,
  "slo_target_pct": 99.9,
  "error_budget_burn_rate": 10.9,
  "generated_at": "2026-05-25T12:01:00"
}
```

### List all scorecards

```bash
GET /api/v1/scorecards
GET /api/v1/scorecards?days=1&limit=5&slo_target_pct=99.0
```

#### Additional query parameters

| Param | Default | Description |
|-------|---------|-------------|
| `source_id` | — | Filter to one source |
| `limit` | `20` | Max sources returned (1–100) |

Response shape: `{ "items": [...scorecards], "total": N }`

## Quick start

### 1. Register a source (if not done yet)

```bash
curl -s -X POST http://localhost:8000/api/v1/sources \
  -H "Content-Type: application/json" \
  -d '{
    "name": "httpbin",
    "base_url": "https://httpbin.org",
    "health_check_path": "/get",
    "probe_interval_seconds": 60
  }' | jq .id
```

### 2. Seed a few probes manually (dev/test only)

```bash
SOURCE_ID=1

# Simulate 5 successful probes
for i in 1 2 3 4 5; do
  curl -s -X POST http://localhost:8000/api/v1/scorecards/samples \
    -H "Content-Type: application/json" \
    -d "{
      \"source_id\": $SOURCE_ID,
      \"sampled_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",
      \"latency_ms\": $((50 + i * 10)),
      \"is_success\": true,
      \"http_status\": 200
    }" > /dev/null
done

# Simulate 1 failure
curl -s -X POST http://localhost:8000/api/v1/scorecards/samples \
  -H "Content-Type: application/json" \
  -d "{
    \"source_id\": $SOURCE_ID,
    \"sampled_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",
    \"latency_ms\": 5000,
    \"is_success\": false,
    \"http_status\": 503,
    \"error_message\": \"Service unavailable\"
  }" > /dev/null
```

### 3. Read the scorecard

```bash
curl -s "http://localhost:8000/api/v1/scorecards/$SOURCE_ID?days=1" \
  | jq '{uptime_pct, p95_latency_ms, error_budget_burn_rate}'
```

## Implementation details

### How aggregation works

Metrics are computed in a **single PostgreSQL aggregate query** per batch of sources:

```sql
SELECT
    source_id,
    COUNT(*)                                                       AS sample_count,
    COUNT(*) FILTER (WHERE NOT is_success)                        AS error_count,
    AVG(latency_ms)                                               AS avg_latency_ms,
    PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY latency_ms ASC) AS p50_latency_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms ASC) AS p95_latency_ms
FROM provider_health_samples
WHERE source_id IN (:ids)
  AND sampled_at >= NOW() - INTERVAL ':days days'
GROUP BY source_id;
```

`PERCENTILE_CONT` uses PostgreSQL's Greenwald-Khanna approximate algorithm — no
row-by-row Python iteration, no `statistics.quantiles`, no in-memory sorting of
thousands of samples.

The list endpoint issues **two queries total** regardless of how many sources are
returned:

1. `SELECT` active `SourceProfile` rows with `LIMIT`.
2. One aggregate `GROUP BY` for all their health samples.

### Indexes used

The query hits the composite index `ix_phs_source_sampled(source_id, sampled_at)`,
which covers both the `IN` filter and the time-window predicate.

### Handling sources with no samples

When a source has no probes in the window, the aggregate query returns no row for
that `source_id`. The repository maps that to `sample_count=0, uptime_pct=100.0,
p95_latency_ms=0.0`.

## Running the tests

Unit tests (no database, fast):

```bash
uv run pytest services/ingestor/tests/unit/test_scorecard_aggregation.py -v
```

Integration tests (require PostgreSQL with `PERCENTILE_CONT` support):

```bash
env -u DATABASE_URL_TEST uv run pytest \
  services/ingestor/tests/integration/test_scorecards_api.py -v \
  -m integration
```

> The integration tests are marked `@pytest.mark.integration` and are skipped
> in the default SQLite-backed test run because SQLite does not support
> `PERCENTILE_CONT`.

## Operational notes

- **Retention**: `provider_health_samples` grows at `sources × probes/day` rows/day.
  A 60-second probe interval on 100 sources produces ~144 000 rows/day. Add a
  periodic `DELETE WHERE sampled_at < NOW() - INTERVAL '90 days'` job when the
  table exceeds tens of millions of rows.

- **Caching**: No Redis caching is added by default. Add
  `SETEX scorecard:{source_id}:{days} 30 <json>` only after measuring p95 query
  time exceeds 50ms under load (see `GET /metrics`).

- **Score freshness**: Scorecards are computed on-request — they always reflect the
  latest probes. There is no background materialization job.
