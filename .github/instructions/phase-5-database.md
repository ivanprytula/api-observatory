# Phase 6 — Database Optimization

**Duration**: 2 weeks
**Goal**: Query optimization (EXPLAIN ANALYZE, indices), pagination, connection pooling, transaction isolation
**Success Metric**: Query latency <50ms (p99), connection pool utilization >60%, zero deadlocks

---

## Core Learning Objective

Master PostgreSQL performance: query planning, index strategies, pagination, connection pooling, and transaction semantics.

---

## Interview Questions

### Core Q: "Optimize Slow Query (5s Latency). Approach?"

**Expected Answer:**

- Run EXPLAIN ANALYZE to see query plan (seq scan bad, index scan good)
- Identify bottleneck: seq scan on large table, missing index, bad join order, or subquery explosion
- Add composite index if filtering on (col1, col2) frequently
- Rewrite subquery to window function (faster, single pass)
- Test: Run EXPLAIN ANALYZE again, verify latency drops, check actual vs estimated rows

**Talking Points:**

- Cost estimation: If actual rows >> estimated, planner chose wrong strategy. Run ANALYZE to update stats.
- Index overhead: Indices speed reads, slow writes (INSERT/UPDATE has index maintenance). Trade-off depends on workload.
- Query tuning order: Indices first (low cost), then query rewrites (medium cost), then schema normalization (high cost).

---

### Follow-Up: "Design Index for Multi-Column Filtering (col1 = X AND col2 = Y AND col3 > Z)"

**Expected Answer:**

- Composite index: `CREATE INDEX idx ON table(col1, col2, col3)` (columns in WHERE-clause order)
- Prefix subsets usable: `(col1, col2, col3)` index also speeds `(col1)` and `(col1, col2)` queries
- Filtering before range: Put equality filters (col1, col2) before range (col3) in index
- Height tuning: If index huge, consider partitioning or removing bloat with REINDEX

**Talking Points:**

- Partial indices: If 95% of rows have status='active', create index WHERE status='active' (smaller, faster)
- BRIN vs B-tree: B-tree good for small tables (<1M rows) or random access. BRIN good for large, naturally sorted tables.
- Index stats: `pg_stat_user_indexes` shows usage (idx_scan, idx_tup_read). Delete unused indices.

---

### Follow-Up: "Connection Pool Exhaustion After Deploy. Fix?"

**Expected Answer:**

- Symptom: CONNECT errors, "too many connections" warning
- Causes: (1) Pool size too small, (2) Queries holding connections too long, (3) Connections not returned (leak)
- Diagnosis: `SELECT count(*) FROM pg_stat_activity` (current connections), compare to pool_size
- Fix: (1) Increase pool_size in config, (2) Reduce query time (index them), (3) Add timeout logic (auto-close idle connections)

**Talking Points:**

- Pool sizing: `pool_size=20, max_overflow=10` means 20 long-lived + 10 temporary (total max 30)
- Connection reuse: Each request gets connection from pool, returns after response ends (implicit in FastAPI)
- Idle timeout: PostgreSQL has `idle_in_transaction_session_timeout` to force-close stalled connections
- Monitoring: `pg_stat_activity` and `asyncpg.get_event_loop().get_debug()` for connection stats

---

## Real life production example — Production-Ready

### Architecture

```text
Analytical query: SELECT source, COUNT(*), AVG(price) FROM records
  GROUP BY source, DATE_TRUNC('day', created_at)
  WHERE created_at > NOW() - INTERVAL '7 days'
  ↓
[SLOW: 5s latency]
  ├─► Seq scan on records (no index)
  ├─► 1M rows filtered, GROUP BY materializes all
  └─► Result: 7K row materialization
  ↓
[OPTIMIZATION]
  1. Add composite index: (created_at, source)
  ├─► WHERE created_at > X uses index_scan (fast)
  ├─► GROUP BY aggregates on indexed rows (partial result set)
  ├─► Latency: 5s → 50ms
```

### Implementation Checklist

- [ ] **Query Analysis: EXPLAIN ANALYZE**

  ```sql
  EXPLAIN ANALYZE
  SELECT source, COUNT(*), AVG(price)
  FROM records
  WHERE created_at > NOW() - INTERVAL '7 days'
  GROUP BY source, DATE_TRUNC('day', created_at)
  ORDER BY source, DATE_TRUNC;
  ```

  Output interpretation:

  ```text
  → GroupAggregate (cost=0.57..25000.00 rows=20 width=100)
    → Index Scan using idx_records_created_at on records (...)
        Index Cond: created_at > NOW() - INTERVAL '7 days'

  Execution time: 5123 ms
  ```

  Key metrics:
  - "cost=0.57..25000.00": Estimated cost (first=startup, last=total)
  - "rows=20": Estimated rows (compare to "actual rows=...")
  - "Seq Scan" = bad (table scan), "Index Scan" = good
  - If actual >> estimated, run ANALYZE to update statistics

- [ ] **Create Composite Indices**

  ```sql
  -- Filtering + ordering
  CREATE INDEX idx_records_created_source
    ON records(created_at DESC, source)
    WHERE state = 'active';  -- Partial index

  -- For pagination (keyset style)
  CREATE INDEX idx_records_pagination
    ON records(pipeline_id, created_at DESC);

  -- For joins
  CREATE INDEX idx_records_source_id
    ON records(source_id)
    INCLUDE (price, description);  -- INCLUDE = covering index
  ```

- [ ] **Pagination Strategy: Keyset (Better Than OFFSET)**

  ```python
  # ❌ WRONG (OFFSET inefficient for large offsets)
  LIMIT 10 OFFSET 99990  # Scans 99990 rows + returns 10

  # ✅ CORRECT (Keyset: remember last cursor)
  WHERE id > last_id AND pipeline_id = X  # Instantly jump to position
  ORDER BY id DESC
  LIMIT 10
  ```

  Implementation:

  ```python
  async def get_records_keyset(db: AsyncSession, pipeline_id: int, cursor: int = 0, limit: int = 10):
      """Keyset pagination (cursor = last_id from previous page)."""
      stmt = select(Record).where(
          (Record.pipeline_id == pipeline_id) &
          (Record.id > cursor)
      ).order_by(Record.id.desc()).limit(limit)

      result = await db.execute(stmt)
      records = result.scalars().all()
      return {
          'records': records,
          'cursor': records[-1].id if records else cursor,  # For next page
      }
  ```

- [ ] **Composite Index Not Used?**

  ```python
  # Query stats
  SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch
  FROM pg_stat_user_indexes
  ORDER BY idx_scan DESC;

  # If idx_scan = 0, index not used (wrong selectivity, or planner prefers seq scan)
  # Fix: Drop unused index or make partial (WHERE clause) to improve selectivity
  ```

- [ ] **Connection Pool Configuration (app/database.py)**

  ```python
  from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

  engine = create_async_engine(
      DATABASE_URL,
      echo=False,
      pool_size=20,              # Long-lived connections
      max_overflow=10,           # Temporary connections
      pool_pre_ping=True,        # Test connection before using (timeout handling)
      echo_pool=False,           # Log pool events
      connect_args={
          'timeout': 10,         # Connection timeout
          'server_settings': {
              'application_name': 'data_pipeline',
              'jit': 'off',      # Disable JIT compilation (simpler plans for simple queries)
          }
      }
  )

  # Async sessionmaker
  async_session = async_sessionmaker(
      engine,
      class_=AsyncSession,
      expire_on_commit=False,    # Don't expire objects (required for async)
  )
  ```

- [ ] **Transaction Isolation (Read Committed vs Serializable)**

  ```python
  # Read Committed (default, fast, allows phantom reads)
  async with db.begin():
      # Reads committed data only
      # Can see data from other transactions committed during query
      pass

  # Serializable (slow, safe, prevents phantoms)
  async with db.begin(isolation_level='SERIALIZABLE'):
      # Behaves as if running alone
      # Retryable errors if conflict detected
      pass
  ```

- [ ] **Monitoring Queries**

  ```python
  # Slow query log (PostgreSQL)
  ALTER DATABASE app SET log_min_duration_statement = 100;  -- Log queries >100ms

  # Query in Python
  logger.info("query_executed", extra={
      'query': statement,
      'duration_ms': duration,
      'rows_returned': row_count,
      'trace_id': trace_id,
  })
  ```

---

## SQL Patterns Checklist (40 Extended)

Master SQL from basic to advanced. **✓ = Implemented; ○ = Understood; ✗ = Need review**

### Foundations (Patterns 1–5)

- [ ] `SELECT ... FROM ... WHERE` — Basic filtering, column selection
- [ ] `ORDER BY ASC/DESC, LIMIT, OFFSET` — Sorting and pagination basics
- [ ] `DISTINCT` — Remove duplicates, count unique values
- [ ] `NULL handling` — IS NULL, IS NOT NULL, COALESCE, NULLIF
- [ ] `CASE/WHEN/ELSE` — Conditional logic in SELECT

### Joins (Patterns 6–10)

- [ ] `INNER JOIN` — Only matching rows from both tables
- [ ] `LEFT JOIN` — All rows from left table + matches from right
- [ ] `RIGHT JOIN` — All rows from right table + matches from left
- [ ] `FULL OUTER JOIN` — All rows from both, fill NULLs for non-matches
- [ ] `CROSS JOIN` — Cartesian product (every left row × every right row)

### Grouping & Aggregation (Patterns 11–15)

- [ ] `GROUP BY ... HAVING` — Group rows and filter groups
- [ ] `COUNT(*)` — Count all rows; COUNT(col) counts non-NULL
- [ ] `SUM, AVG, MIN, MAX` — Aggregate functions
- [ ] `STRING_AGG` — Concatenate column values into string per group
- [ ] `ARRAY_AGG` — Collect values into array per group

### Subqueries (Patterns 16–20)

- [ ] `Scalar subquery` — Returns 1 row/column, use in SELECT/WHERE
- [ ] `IN subquery` — WHERE col IN (SELECT ...) for multiple matches
- [ ] `EXISTS subquery` — More efficient than IN for large result sets
- [ ] `NOT IN / NOT EXISTS` — Inverted logic
- [ ] `Correlated subquery` — References outer query table (slower, use WITH instead)

### Common Table Expressions (Patterns 21–25)

- [ ] `WITH (CTE)` — Named temporary result set, referenced later
- [ ] `Multiple CTEs` — Chain CTEs (WITH cte1 AS (...) , cte2 AS (...))
- [ ] `Recursive CTE` — Self-referential, useful for hierarchies (org charts, tree walks)
- [ ] `CTE vs subquery` — When to use CTE (readability, reusability) vs subquery (performance)
- [ ] `CTE with window functions` — Combine CTEs and analytical queries

### Set Operations (Patterns 26–28)

- [ ] `UNION` — Combine results, remove duplicates
- [ ] `UNION ALL` — Combine results, keep duplicates (faster)
- [ ] `EXCEPT / INTERSECT` — Set difference and intersection

### Window Functions (Patterns 29–35)

- [ ] `ROW_NUMBER()` — Unique rank per row (1, 2, 3, ...)
- [ ] `RANK() / DENSE_RANK()` — Rank with ties; RANK skips, DENSE_RANK doesn't
- [ ] `LAG / LEAD` — Access previous/next row in partition
- [ ] `FIRST_VALUE / LAST_VALUE` — First/last value in window
- [ ] `PARTITION BY ... ORDER BY` — Define window boundaries
- [ ] `Running aggregate` — SUM(...) OVER (ORDER BY date ROWS BETWEEN ...) for cumulative totals
- [ ] `Percentile functions` — PERCENTILE_CONT, PERCENTILE_DISC for analytics

### Indexing & Query Planning (Patterns 36–38)

- [ ] `Composite index` — Index on (col1, col2, col3); prefix subsets also indexed
- [ ] `Partial index` — WHERE clause in index definition to reduce size (WHERE active=true)
- [ ] `Covering index` — INCLUDE clause to have all SELECT columns in index (avoid table lookup)

### Advanced Query Patterns (Patterns 39–40)

- [ ] `Keyset pagination` — WHERE id > last_id (faster than OFFSET for large offsets)
- [ ] `EXPLAIN ANALYZE` — Read query plans, identify seq scans, check actual vs estimated rows

---

### Checklist Usage

**Per pattern, code implements or demonstrates:**

| Pattern               | SQL Example                                                                 | Python Code                                          | Test Case         | Interview Q                   |
| --------------------- | --------------------------------------------------------------------------- | ---------------------------------------------------- | ----------------- | ----------------------------- |
| 1. SELECT WHERE       | `SELECT * FROM records WHERE price > 100`                                   | `stmt = select(Record).where(Record.price > 100)`    | Test 5 filters    | "Filter 1M rows efficiently?" |
| 2. ORDER BY LIMIT     | `SELECT * FROM records ORDER BY created_at DESC LIMIT 10`                   | `.order_by(Record.created_at.desc()).limit(10)`      | Pagination test   | "Paginate 1M rows?"           |
| 6. INNER JOIN         | `SELECT * FROM records r JOIN sources s ON r.source_id = s.id`              | `select(Record, Source).join(Source)`                | Multi-table test  | "Join logic?"                 |
| 11. GROUP BY          | `SELECT source, COUNT(*) FROM records GROUP BY source HAVING COUNT(*) > 10` | `.group_by(Record.source)`                           | Aggregation test  | "GROUP BY vs window?"         |
| 21. CTE               | `WITH active AS (...) SELECT * FROM active`                                 | `select(...).from_(cte)`                             | CTE test          | "CTE vs subquery?"            |
| 29. ROW_NUMBER        | `SELECT *, ROW_NUMBER() OVER (ORDER BY created_at) FROM records`            | `func.row_number().over(order_by=Record.created_at)` | Rank test         | "ROW_NUMBER vs RANK?"         |
| 36. Composite Index   | `CREATE INDEX idx ON records(source_id, created_at)`                        | Run EXPLAIN ANALYZE, verify index_scan               | Index usage test  | "Index ordering?"             |
| 39. Keyset Pagination | `SELECT * FROM records WHERE id > 999 LIMIT 10`                             | `(Record.id > cursor).limit(10)`                     | Large offset test | "Why keyset > OFFSET?"        |

---

## Weekly Checklist

### Week 1: SQL Foundations + Query Analysis + Indices

**Goal**: Master 20/40 SQL patterns (Foundations through Subqueries)

- [ ] Study SQL Patterns 1–5 (SELECT, WHERE, ORDER BY, DISTINCT, CASE): write 5 queries per pattern
- [ ] Study SQL Patterns 6–10 (JOIN types): write joins covering INNER/LEFT/RIGHT/FULL/CROSS
- [ ] Study SQL Patterns 11–15 (GROUP BY, aggregates): GROUP BY with HAVING, COUNT vs COUNT(col)
- [ ] Study SQL Patterns 16–20 (Subqueries): scalar, IN, EXISTS, NOT IN, correlated
- [ ] EXPLAIN ANALYZE on 5 slow queries (analytics, filtering, joins)
- [ ] Identify bottleneck for each (seq scan, missing index, bad join order)
- [ ] Create composite indices (3–5 indices covering main query patterns)
- [ ] Test: Re-run EXPLAIN ANALYZE, verify latency drops
- [ ] Index stats: Verify indices used (idx_scan > 0 from pg_stat_user_indexes)
- [ ] Interview Q: "Optimize slow query?" → Answer drafted with query plan
- [ ] Commits: 6–8 (benchmark queries, indices, query rewrites, tests)

### Week 2: CTE + Window Functions + Pagination + Performance

**Goal**: Master remaining 20/40 SQL patterns (CTEs through EXPLAIN ANALYZE)

- [ ] Study SQL Patterns 21–28 (CTEs, set operations): WITH clause, recursive CTE, UNION, EXCEPT
- [ ] Study SQL Patterns 29–35 (Window functions): ROW_NUMBER, RANK, LAG/LEAD, running aggregates
- [ ] Study SQL Patterns 36–40 (Indexing, keyset): composite, partial, covering indices, keyset pagination
- [ ] Rewrite 5 subqueries → CTEs (readability, reusability)
- [ ] Implement window functions for analytics (replacing subqueries)
- [ ] Keyset pagination implementation (cursor-based, not OFFSET)
- [ ] Connection pool tuning (measure pool utilization, adjust max)
- [ ] Transaction isolation testing (phantom reads under concurrency)
- [ ] Load test: 1000 concurrent requests, monitor connection count (should stay < pool_size)
- [ ] Deadlock detection: Run chaos test (concurrent writes same rows, verify retry logic)
- [ ] Structured logging: Every query logged with duration, trace ID
- [ ] Interview Q: "All 40 patterns: which would you use to...?" → Full repertoire ready
- [ ] Commits: 5–7 (CTE rewrites, window functions, pagination, pool tuning, tests)
- [ ] Portfolio item + LinkedIn post (feature: "Mastered 40 SQL patterns for interview prep")

---

## Success Metrics

| Metric                      | Target | How to Measure                                                 |
| --------------------------- | ------ | -------------------------------------------------------------- |
| SQL patterns mastered       | 40/40  | Can write/explain all 40 patterns from memory                  |
| Query latency (p99)         | <50ms  | EXPLAIN ANALYZE + load test (measure end-to-end)               |
| Index usage                 | 100%   | pg_stat_user_indexes: all created indices have idx_scan > 0    |
| Connection pool utilization | 60–80% | Monitor `SELECT count(*) FROM pg_stat_activity` during peak    |
| Deadlock rate               | 0      | Monitor PostgreSQL logs, concurrent write tests                |
| Pagination offset           | 0 uses | All list endpoints use keyset (cursor-based), not LIMIT OFFSET |
| Commit count                | 11–15  | 1 per optimization                                             |

---

## Gotchas + Fixes

### Gotcha 1: "Index Not Being Used"

**Symptom**: EXPLAIN ANALYZE shows Seq Scan despite index existing.
**Cause**: Planner estimates seq scan cheaper (selectivity <5%), or statistics stale.
**Fix**: Run `ANALYZE table_name` to update statistics, or make index partial (WHERE active=true) to improve selectivity.

### Gotcha 2: "Connection 'too many connections' After Deploy"

**Symptom**: CONNECT errors start happening.
**Cause**: Pool size too small or connections not released (query timeout, no explicit close).
**Fix**: Increase pool_size, add query timeout (`statement_timeout=10000` in connection string), add pool_pre_ping=True.

### Gotcha 3: "OFFSET Pagination Slow on page 1000+"

**Symptom**: `LIMIT 10 OFFSET 99990` takes 10s.
**Cause**: Database scans 99990 rows (overhead) before returning 10.
**Fix**: Switch to keyset pagination (WHERE id > cursor) → instant jumps.

### Gotcha 4: "Composite Index Bloats After Deletes"

**Symptom**: Index huge (2GB), query still slow.
**Cause**: Index contains stale entries from deleted rows.
**Fix**: `REINDEX INDEX idx_name` (rebuild), or `VACUUM ANALYZE` (reclaim space).

---

## Cleanup (End of Phase 6)

```bash
# Check index bloat
SELECT schemaname, tablename, indexname,
  ROUND(100.0 * (CASE WHEN otta > 0 THEN sml.relpages::float / otta
    ELSE 0.0 END), 2) AS table_bloat_ratio
FROM pg_class;

# Remove unused indices
DROP INDEX idx_name;
```

---

## Metrics to Monitor Ongoing

- Query latency p99: Alert if > 100ms
- Active connections: Alert if > pool_size × 0.9 (approaching limit)
- Slow queries: Monitor via `log_min_duration_statement` log file
- Index utilization: Alert if any index has idx_scan = 0 after 7 days (unused, consider dropping)

---

## Next Phase

**Phase 7: Security + Infrastructure**
JWT + refresh tokens, rate limiting, secrets rotation, Terraform multi-environment deployment.

**Reference**: Phase 6 queries optimized (p99 <50ms) = ready for Phase 7.
