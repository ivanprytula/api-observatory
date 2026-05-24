---
description: "10-week middle-tier interview prep: SQL/pytest checklists, real life production examples (GraphQL/gRPC/WebSockets/Celery), document-as-you-go tracking"
applyTo: "docs/**/*.md, .github/**/*.md"
---

# Middle Tier Grind — 10-Week Tracking

Compressed: 70 days (10 days/phase). Each phase = real life production examples + portfolio artifact + interview prep.

## Phase Timeline & Interview Questions

| Phase        | Weeks | Core Q                            | Follow-ups                                  | Real life production examples                       |
| ------------ | ----- | --------------------------------- | ------------------------------------------- | --------------------------------------------------- |
| 1: Events    | 1–2   | "Design ETL for 1000+ events/sec" | "Consumer lag?", "Exactly-once?"            | Celery + Redpanda + DLQ                             |
| 2: Scrapers  | 3–4   | "Scraper for 100K URLs?"          | "Prevent ban?", "Concurrent vs sequential?" | GraphQL status + Playwright + Semaphore             |
| Docker+CI    | 5–6   | "Dev → prod pipeline?"            | "Image versioning?", "Rollback?"            | WebSocket + GitHub Actions + ECR                    |
| 3: AI+Vector | 7–8   | "Semantic search 100K docs?"      | "Cache invalidation?", "Why gRPC vs REST?"  | gRPC embeddings + Qdrant + LRU cache                |
| 4: Testing   | 9–10  | "Test external API call?"         | "Async fixture cleanup?", "Mock gRPC?"      | Celery mocking + parametrized fixtures              |
| 5: Database  | 11–12 | "Slow query (5s). Fix."           | "Read EXPLAIN?", "Index vs rewrite?"        | EXPLAIN ANALYZE + composite index + window function |
| 6: Security  | 13–14 | "JWT auth multi-service?"         | "Key rotation?", "Why refresh tokens?"      | JWT + refresh + rate limit + Pydantic validation    |
| 7: Terraform | 15–16 | "Code → production?"              | "State lock?", "Secrets rotation?"          | Terraform modules + multi-env + GitHub CD           |

---

## SQL Patterns Checklist (40 Extended)

✓ = Implemented in code; ○ = Understood; ✗ = Need review

### Foundations (1–5)

- [ ] SELECT/WHERE/ORDER BY/LIMIT/OFFSET
- [ ] DISTINCT, NULL handling (IS NULL, COALESCE, NULLIF)
- [ ] CASE/WHEN/ELSE conditional logic
- [ ] ORDER BY ASC/DESC with multiple columns
- [ ] Debugging with LIMIT and OFFSET

### Joins (6–10)

- [ ] INNER JOIN (only matches)
- [ ] LEFT JOIN (all left + matches)
- [ ] RIGHT JOIN (all right + matches)
- [ ] FULL OUTER JOIN (all from both)
- [ ] CROSS JOIN (Cartesian product)

### Grouping & Aggregation (11–15)

- [ ] GROUP BY with HAVING filters
- [ ] COUNT(*), COUNT(col), SUM, AVG, MIN, MAX
- [ ] STRING_AGG, ARRAY_AGG (group-level concatenation)
- [ ] GROUP BY multiple columns
- [ ] Aggregate window functions

### Subqueries (16–20)

- [ ] Scalar subquery (single value in WHERE/SELECT)
- [ ] IN subquery (matching multiple values)
- [ ] EXISTS subquery (efficient membership test)
- [ ] NOT IN / NOT EXISTS (inverted logic)
- [ ] Correlated subquery (references outer table, slower)

### Common Table Expressions (21–25)

- [ ] WITH (CTE) basic syntax
- [ ] Multiple CTEs (chain WITH clauses)
- [ ] Recursive CTE (hierarchies, tree walks)
- [ ] CTE vs subquery trade-offs
- [ ] CTE with window functions combined

### Set Operations (26–28)

- [ ] UNION (combine, remove duplicates)
- [ ] UNION ALL (combine, keep duplicates)
- [ ] EXCEPT / INTERSECT (set difference/intersection)

### Window Functions (29–35)

- [ ] ROW_NUMBER() (sequential rank)
- [ ] RANK() / DENSE_RANK() (tied ranks)
- [ ] LAG / LEAD (access prev/next row)
- [ ] FIRST_VALUE / LAST_VALUE (boundary values)
- [ ] PARTITION BY / ORDER BY (window frames)
- [ ] Running aggregate (cumulative SUM)
- [ ] PERCENTILE functions (analytics)

### Indexing & Query Planning (36–38)

- [ ] Composite index (multi-column, prefix subsets)
- [ ] Partial index (WHERE clause, reduced size)
- [ ] Covering index (INCLUDE clause, no table lookup)

### Advanced Patterns (39–40)

- [ ] Keyset pagination (WHERE id > cursor, faster than OFFSET)
- [ ] EXPLAIN ANALYZE (query plans, seq scan vs index scan)

---

## Pytest Fixtures (10)

- [ ] `async_session` — AsyncSession for database tests
- [ ] `client` — HTTPClient/AsyncClient for API tests
- [ ] `mock_external_api` — Mock external HTTP calls
- [ ] `fixture_with_cleanup` — Ensure cleanup runs after test
- [ ] `parametrized_fixture` — @pytest.mark.parametrize patterns
- [ ] `fixture_scope` — function vs session vs module scopes
- [ ] `tmp_file_fixture` — Temporary file creation
- [ ] `time_travel_fixture` — freezegun time manipulation
- [ ] `caplog_fixture` — Capture log output
- [ ] `db_transaction_rollback` — Isolation in tests (rollback after each test)

---

## Async Gotchas (5)

| Gotcha                          | Problem                                     | Fix                                                    | Example                                     |
| ------------------------------- | ------------------------------------------- | ------------------------------------------------------ | ------------------------------------------- |
| **Greenlet without event loop** | AttributeError accessing model after commit | Set `expire_on_commit=False` on AsyncSessionLocal      | `sessionmaker(..., expire_on_commit=False)` |
| **Sync code in async**          | Event loop blocks, app hangs                | Use `asyncio.to_thread(sync_func)`                     | `await asyncio.to_thread(blocking_db_call)` |
| **Task not awaited**            | Warning, function doesn't run               | Always `await` or `asyncio.create_task()`              | `await coroutine()` not `coroutine()`       |
| **Cancellation not propagated** | Task keeps running after cancel             | Check `current_task().cancel()`, handle CancelledError | `try: ... except asyncio.CancelledError:`   |
| **Event loop closed**           | RuntimeError after test cleanup             | Use `asyncio_mode = "auto"` in pytest.ini              | `asyncio_mode = auto` in pyproject.toml     |

---

## Weekly Interview Checklist

### Week 1–2: Phase 1 (Event Streaming)

- [ ] **Core Q Prepared**: "Design real-time ETL for 1000+ events/sec" — sketch answer
- [ ] **Follow-up 1**: "What's consumer lag? Why monitor it?"
- [ ] **Follow-up 2**: "Exactly-once vs at-least-once delivery? Trade-offs?"
- [ ] **Talking Points**: Consumer lag calculation, topic partitioning strategy, offset management, partition rebalancing

### Week 3–4: Phase 2 (Scrapers)

- [ ] **Core Q Prepared**: "Design scraper for 100K URLs without ban"
- [ ] **Follow-up 1**: "How prevent request ban?"
- [ ] **Follow-up 2**: "Concurrent vs sequential trade-offs?"
- [ ] **Talking Points**: Rate limiting (semaphore, backoff), Pydantic validation as ETL filter, exponential backoff algorithm

### Week 5–6: Docker+CI

- [ ] **Core Q Prepared**: "Walk me through dev → prod pipeline"
- [ ] **Follow-up 1**: "How handle Docker image versioning?"
- [ ] **Follow-up 2**: "Rollback strategy?"
- [ ] **Talking Points**: CI/CD stages (test, lint, build, push), Docker layer caching, registry artifacts, GitHub Actions syntax

### Week 7–8: Phase 3 (AI+Vector)

- [ ] **Core Q Prepared**: "Design semantic search over 100K docs"
- [ ] **Follow-up 1**: "Cache invalidation strategy?"
- [ ] **Follow-up 2**: "Why gRPC vs REST for embeddings?"
- [ ] **Talking Points**: Embedding model trade-offs (speed, token cost), vector DB indexing (IVF, HNSW), LRU cache patterns, similarity metrics

### Week 9–10: Phase 4 (Testing)

- [ ] **Core Q Prepared**: "How test function calling external API?"
- [ ] **Follow-up 1**: "Async fixture cleanup pitfalls?"
- [ ] **Follow-up 2**: "How mock gRPC calls?"
- [ ] **Talking Points**: Mocking strategies (unittest.mock, pytest-asyncio), parametrization, time manipulation, error scenarios

### Week 11–12: Phase 5 (Database)

- [ ] **Core Q Prepared**: "Slow query (5s). Fix."
- [ ] **Follow-up 1**: "How read EXPLAIN ANALYZE output?"
- [ ] **Follow-up 2**: "When add index vs rewrite query?"
- [ ] **Talking Points**: Query execution plans, index strategy, window functions vs subqueries, transaction isolation

### Week 13–14: Phase 6 (Security)

- [ ] **Core Q Prepared**: "Design JWT auth for multi-service"
- [ ] **Follow-up 1**: "How handle key rotation?"
- [ ] **Follow-up 2**: "Why refresh tokens?"
- [ ] **Talking Points**: JWT structure (not encrypted), refresh token flow, rate limiting algorithms, secret management

### Week 15–16: Phase 7 (Terraform)

- [ ] **Core Q Prepared**: "Walk me through code → production"
- [ ] **Follow-up 1**: "How handle Terraform state lock?"
- [ ] **Follow-up 2**: "Secrets rotation in IaC?"
- [ ] **Talking Points**: Terraform state management, multi-env variables, rollback scenarios, infrastructure versioning

---

## Success Metrics (Track Weekly)

| Metric                             | Target  | Status |
| ---------------------------------- | ------- | ------ |
| Interview Q answered cold per week | 4/5 ✓   |        |
| Code commits/phase                 | 8–15    |        |
| Tests passing                      | 100%    |        |
| SQL patterns implemented           | 40/40   |        |
| Pytest fixtures demonstrated       | 10/10   |        |
| Async gotchas with examples        | 5/5     |        |
| LinkedIn posts                     | 1/phase |        |
| Portfolio items                    | 1/phase |        |

---

## Final CV Narrative

**Profile:** Backend engineer shipping multi-service data platforms. Specialized in event streaming (Redpanda), data pipelines (validation, transform), async Python (asyncio, proper cancellation), PostgreSQL optimization (indexing, queries), infrastructure automation (Terraform, CI/CD, Docker). Known for debugging production issues and shipping tested, scalable code.

**Key Achievement (Data Zoo Platform):** "Architected and shipped multi-service data platform: event-streaming foundation (Redpanda) processing 10M+ events/day, AI gateway with semantic search (Qdrant + embeddings), distributed tracing (OpenTelemetry) enabling sub-100ms debugging across services, infrastructure-as-code deployment (Terraform → AWS Fargate), supporting 2x QPS without adding servers through database optimization and resilience patterns."

---

## Tips for Success

1. **Print this checklist weekly** — Review on Monday, track progress Friday
2. **Interview Q practice**: Spend 10 min daily articulating core Q + follow-ups
3. **Document learning**: Screenshot or note key insights (use in portfolio items)
4. **Commit messages**: Use templates from `docs/templates/github-commit-template.md`
5. **LinkedIn cadence**: Post on Friday afternoon (8 posts total, 1 per phase)
6. **Code quality**: Aim for 100% tests passing; quality > quantity
