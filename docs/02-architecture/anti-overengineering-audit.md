# Anti-Overengineering Audit

Flags files and abstractions that exceed the project's own guidelines or show
signs of premature generalization. This is a snapshot, not a refactor plan.

## File Size Violations

Production files exceeding the ~300-line guideline:

| File | Lines | Risk | Recommended action |
| --- | --- | --- | --- |
| `repositories/observations.py` | 884 | High — mixed CRUD, query helpers, materialized views, CTEs | Split into `crud.py` + `queries.py` |
| `repositories/reporting.py` | 851 | High — multiple report types in one module | Split by report domain |
| `routers/observations_v2.py` | 830 | Medium — many endpoint groups | Group by capability (rate-limit demos, enrichment, upsert) |
| `main.py` | 776 | Medium — startup, router wiring, OpenAPI tags | Acceptable for composition root; extract `_OPENAPI_TAGS` if it grows |
| `routers/observations.py` | 681 | Medium — CRUD + auth + validation + batch | Already large; defer split until next auth consolidation |
| `repositories/contract_drift.py` | 612 | Medium — snapshots, baselines, drift queries | Split into `snapshots.py` + `baselines.py` |
| `routers/analytics.py` | 599 | Medium — scorecards, insights, reporting | Split by query type |
| `cache.py` | 531 | Medium — Redis client, fakeredis fallback, decorators | Extract `fakeredis` setup to test fixture |
| `fetch.py` | 524 | Medium — HTTP client, circuit breaker, retry, mTLS | Extract mTLS transport to separate module |
| `api_schemas/reporting.py` | 505 | Medium — many response models | Group by report domain |
| `api_schemas/observations.py` | 500 | Medium — request/response + scraper schema | Split scraper schema if kept |
| `auth.py` | 483 | Medium — JWT, session, API key, bearer, internal auth | Acceptable; each mechanism is small and independent |
| `security/abuse_detection.py` | 376 | Medium — detectors, signal storage, rate limiting | Split detectors from storage |
| `repositories/notification_delivery.py` | 370 | Medium — outbox, inbox, delivery repo | Split outbox/inbox/delivery |
| `notifications.py` | 345 | Medium — provider adapters + dispatch boundary | Extract provider adapters to `providers/` |
| `security/api_keys.py` | 341 | Medium — CRUD + scopes + hashing | Acceptable for focused auth module |
| `routers/reporting.py` | 327 | Medium — reporting endpoints | Split by report type |
| `routers/source_registry.py` | 302 | Borderline — source CRUD + SSRF validation | Acceptable; near threshold |
| `transformations/tabular.py` | 301 | Borderline — tabular strategies | Acceptable; near threshold |

## Abstractions with Fewer Than 3 Callers

| Symbol | Defined in | Callers | Verdict |
| --- | --- | --- | --- |
| `RetentionVerificationError` | `jobs/retention.py` | 1 (same module) | Keep — domain-specific error for archive verification |
| `UnsupportedETLBackendError` | `transformations/tabular.py` | 2 | Keep — ETL backend abstraction is lab feature |
| `S3Error` (re-export) | `cache.py` | 2 | Flag — Minio-specific leak in cache module; move to `storage/` |
| `ScraperTimeoutError` | `scrapers/__init__.py` | 2 | Remove — scraper endpoints deleted; no longer needed |
| `NotificationProviderError` | `notifications.py` | 4 | Keep — provider abstraction has 4 adapters |
| `BulkheadRejectedError` | `libs/platform/bulkhead.py` | 5 | Keep — shared resilience primitive |
| `RetryBudgetExceededError` | `libs/platform/retry.py` | 3 | Keep — retry budget is used by circuit breaker + decorator |
| `TimestampMixin` | `models/base.py` | 15 | Keep — shared ORM concern |
| `PriorityJobQueue` | `jobs/queue.py` | 2 | Keep — command pattern is learning exercise; <3 callers expected |

## Patterns to Watch

1. **Repository classes growing by endpoint count**: `observations.py` and `reporting.py` both
   accreted queries as endpoints were added. This is the classic "God repository" anti-pattern.
   Split criteria: when a single repository file exceeds 600 lines or imports more than 8
   distinct query patterns.

2. **Router files growing by feature flag**: `observations.py` and `observations_v2.py` both
   contain feature-gated endpoints. Consider splitting `demo_router` into its own module
   (`routers/observations_demo.py`) to keep the production router focused.

3. **Auth module as kitchen sink**: `auth.py` contains JWT, session, API key, bearer token,
   and internal service auth. Each mechanism is small, but the module is 483 lines. Defer
   split until the Bearer token endpoint is moved off the production router.

4. **Cache module leaking storage details**: `S3Error` re-export in `cache.py` couples the
   cache layer to Minio/S3. Move to `storage/` module or catch and re-raise as
   `CacheBackendError`.

## What This Audit Does NOT Recommend

- Splitting `models.py` or `jobs.py` — already done in this session.
- Removing any abstractions — all flagged symbols are in active use or serve as learning
  exercises with clear purpose.
- Rewriting repositories — the God repository pattern is a known debt, but the query
  surface is stable and well-tested. Split only when adding a new domain boundary.
