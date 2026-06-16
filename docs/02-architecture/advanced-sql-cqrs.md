# Phase 5: Advanced SQL + CQRS Read Side

Track: E — Archive and Historical Snapshots

## Summary

Phase 5 introduces production-grade analytics capabilities through advanced PostgreSQL features and CQRS architecture. The ingestor remains unchanged; a new read-optimized `analytics` service handles all analytics queries using materialized views, window functions, and CTEs.

## Key Features Implemented

### 1. Materialized Views (Pre-aggregated Data)

**`observations_hourly_stats`** — Hourly aggregation materialized view

```sql
WITH hourly_observations AS (
    SELECT date_trunc('hour', timestamp) AS hour, ...
    FROM observations WHERE deleted_at IS NULL
),
hour_stats AS (
    SELECT hour,
           COUNT(*) as observation_count,
           COUNT(*) FILTER (WHERE processed = true) AS processed_count,
           AVG(value), MIN(value), MAX(value)
    FROM hourly_observations
    GROUP BY hour
)
SELECT hour, observation_count, processed_pct, avg_value, ...
```

Benefits:

- Fast dashboard queries (pre-computed aggregates)
- Manual refresh via `POST /analytics/refresh-materialized-view`
- Eventual consistency model (reads lag writes by up to refresh interval)

### 2. Table Partitioning (Range by Month)

**`observations_archive`** — Partitioned table for historical observations

- Monthly range partitioning (e.g., `observations_archive_202504`, `observations_archive_202505`)
- Queries automatically select relevant partitions (partition pruning)
- Old partitions can be archived/deleted independently
- 12-month partition plan pre-created

Benefits:

- Faster queries on recent data (smaller indexes)
- Archive strategy: Move 3+ month-old partitions to cold storage
- Predictable maintenance windows

### 3. Window Functions (Advanced Analytics)

**PERCENT_RANK()** — Percentile rankings within source

```sql
SELECT id, value,
       PERCENT_RANK() OVER (PARTITION BY source ORDER BY value DESC) AS percentile_rank
FROM observations
```

Returns 0.0 (lowest 0%) to 1.0 (highest 100%) for each value relative to source.

**RANK()** — Dense ranking (handles ties)

```sql
SELECT id, source, value,
       RANK() OVER (PARTITION BY source ORDER BY value DESC) AS rank
FROM observations
```

**Compared to ROW_NUMBER():** RANK assigns same rank to ties; ROW_NUMBER always increments.

### 4. Common Table Expressions (CTEs) — Multi-step Aggregations

Three endpoints demonstrate CTE patterns:

| Endpoint                   | CTE Strategy                                | Use Case                  |
| -------------------------- | ------------------------------------------- | ------------------------- |
| `/analytics/summary`       | Hourly bucketing → aggregation → enrichment | Dashboard top-level stats |
| `/analytics/percentile`    | Direct window function                      | Outlier detection         |
| `/analytics/top-by-source` | Filter → rank → postprocess                 | Top observations per source    |

### 5. pgvector Extension (Comparison with Qdrant)

Phase 5 adds the PostgreSQL `pgvector` extension for vector similarity search:

```sql
CREATE EXTENSION vector;

-- Store vectors in PostgreSQL (as alternative to Qdrant)
ALTER TABLE observations ADD COLUMN embedding vector(384);

-- Semantic search (vs. Qdrant's specialized approach)
SELECT id, source, similarity(embedding, query_vector) AS score
FROM observations
WHERE embedding <-> query_vector < 1.0
ORDER BY embedding <-> query_vector
LIMIT 10;
```

**See** ADR 002 (Qdrant vs pgvector) for detailed trade-offs.

## Architecture: CQRS Pattern

Write Side (Unchanged):

```text
POST /api/v1/observations
  ↓
ingestor (app/) saves to observations table
  ↓
Publishes observation.created event → Kafka topic
```

Read Side (New):

```text
analytics service (read-only)
  ├── GET /analytics/summary → materialized view
  ├── GET /analytics/percentile → window function
  ├── GET /analytics/top-by-source → RANK() OVER
  └── POST /refresh-materialized-view → manual refresh
```

Eventual Consistency:

- Writes immediately visible in raw `observations` table
- Aggregates in `observations_hourly_stats` updated on-demand
- Reads may show data 1-60 minutes old depending on refresh frequency

## API Endpoints

### `GET /analytics/summary?hours=24`

Hourly aggregated stats (CTE-based multi-step aggregation).

```json
{
  "hours_back": 24,
  "summary": [
    {
      "hour": "2026-04-21T12:00:00",
      "observation_count": 156,
      "processed_count": 145,
      "processed_pct": 92.95,
      "avg_value": 42.5,
      "min_value": 0,
      "max_value": 100,
      "unique_sources": 8
    }
  ]
}
```

### `GET /analytics/percentile?source=api-logs`

Percentile rankings using PERCENT_RANK().

```json
{
  "source": "api-logs",
  "count": 42,
  "observations": [
    {
      "id": 1,
      "timestamp": "2026-04-21T10:30:00",
      "value": 99.5,
      "percentile_rank": 0.9975
    }
  ]
}
```

### `GET /analytics/top-by-source?limit=5&hours=168`

Top N observations per source (RANK() OVER).

```json
{
  "limit_per_source": 5,
  "by_source": {
    "api-logs": [
      {"id": 42, "rank": 1, "value": 99.5},
      {"id": 43, "rank": 2, "value": 98.2}
    ],
    "metrics": [
      {"id": 51, "rank": 1, "value": 87.3}
    ]
  }
}
```

### `POST /analytics/refresh-materialized-view`

Force refresh (blocking):

```json
{"status": "success", "message": "Materialized view refreshed"}
```

### `GET /analytics/materialized-view-stats?limit=24`

Query pre-computed view directly.

## Database Migrations

Run the migration to create views, partitions, and extensions:

```bash
uv run alembic upgrade head
```

### Migration: `20260421_000001_phase5_advanced_sql_cqrs.py`

- Creates `observations_hourly_stats` materialized view
- Creates `observations_archive` partitioned table (12-month plan)
- Enables `pgvector` extension

## Running Phase 5

### Local Stack

```bash
# Apply migrations
uv run alembic upgrade head

# Start services (including analytics on port 8005)
docker compose up --build

# Query the analytics API
curl http://127.0.0.1:8005/analytics/summary?hours=24
curl http://127.0.0.1:8005/analytics/percentile?source=test-source
curl http://127.0.0.1:8005/analytics/top-by-source
```

### Verification

1. **Materialized View Ready:**

   ```bash
   psql -U postgres -d data_pipeline -c "SELECT COUNT(*) FROM observations_hourly_stats"
   ```

2. **Partitions Created:**

   ```bash
   psql -U postgres -d data_pipeline -c "\dt observations_archive*"
   ```

3. **Query API Healthy:**

   ```bash
   curl http://127.0.0.1:8005/health
   # {"status": "healthy", "service": "analytics"}
   ```

## Advanced Python Patterns

### 1. Window Functions (Analytics)

```python
# From analytics.py: Using PERCENT_RANK
PERCENT_RANK() OVER (PARTITION BY source ORDER BY value DESC)
```

Used in real-world scenarios:

- Recommendation systems (top 10% products)
- Anomaly detection (outliers > 95th percentile)
- Performance tracking (distribution analysis)

### 2. CTEs (Query Composition)

```python
# Multi-step analytics: bucket → aggregate → enrich
WITH step1 AS (...), step2 AS (...), step3 AS (...)
SELECT FROM step3
```

**DSA parallel:** Like recursive problem decomposition — each CTE is a layer.

### 3. Partitioning (Data Architecture)

```sql
-- Monthly partitioning enables:
-- - Parallel queries across partitions
-- - Independent archive/delete operations
-- - Predictable query performance
PARTITION BY RANGE (timestamp)
```

**DSA parallel:** Like B-tree node splitting — data naturally separates by time.

## Future Extensions (Phase 6+)

- **Kafka Consumer in analytics:** Subscribe to `observation.created` events, maintain read-optimized projections in real-time
- **REFRESH MATERIALIZED VIEW CONCURRENTLY:** Requires unique index on view; removes blocking refreshes
- **Background Tasks:** APScheduler for hourly materialized view refresh
- **EXPLAIN ANALYZE** integration: Dashboard showing expensive queries
- **Query result caching:** Cache cache layer over heavy aggregations

## Related ADRs

- ADR 002 (Qdrant vs pgvector) — Vector store decision
