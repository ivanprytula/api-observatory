# Performance and Failure Practice

This is the canonical worksheet for measurement and recovery exercises. Scripts and tests provide
repeatable mechanisms; a number is a baseline only when its environment and date are recorded.

## Query Plan Exercise

Profile the scorecard query against PostgreSQL, not SQLite. The focused proof is
[`test_query_analysis.py`](../../services/ingestor/tests/integration/observations/test_query_analysis.py);
use the test runner documented in [Development Workflows](dev-workflows.md).

For a populated local database, capture `EXPLAIN (ANALYZE, BUFFERS)` for the rolling scorecard
aggregation. Record row count, window, indexes used, planning/execution time, buffer hits/reads, and
whether the plan changes at 10x generated samples. Never paste an isolated plan without the query,
schema, cardinality, and environment.

The tenant incident listing has a separate PostgreSQL proof in
[`test_query_analysis.py`](../../services/ingestor/tests/integration/observations/test_query_analysis.py).
It seeds 40 matching incidents among 1,040 rows, then captures the bounded
`tenant_id` + `status` query with `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`. The expected plan uses
`ix_dependency_incidents_tenant_status`; this demonstrates index eligibility, not a portable latency
target. Record any manually captured plan with the commit, row distribution, PostgreSQL image, and
container resource limits.

## Bounded Load Baseline

Use the existing
[`k6-ci-smoke.js`](../../scripts/load/k6-ci-smoke.js) and
[`k6-observations-load.js`](../../scripts/load/k6-observations-load.js) workloads. Their CI owner is
[`assurance.yml`](../../.github/workflows/assurance.yml). The latter is an explicit local lab:
`BEARER_TOKEN="$(just smoke-token)" just --justfile just/labs.just lab-load`.

Record commit, hardware/container limits, concurrency, duration, dataset size, p50/p95/p99, error
rate, CPU/memory, connection-pool use, and queue depth. Do not convert a laptop result into a
production capacity claim.

## Failure Matrix

| Dependency | Inject | Observe | Recovery proof |
| --- | --- | --- | --- |
| External API | timeout, 5xx, slow response | probe result, breaker, incident transition | successful probe and incident resolution time |
| PostgreSQL | unavailable/slow query | readiness, HTTP errors, pool wait, traces | migration/schema intact and requests recover |
| Redis | stop cache | fail-open logs, cache metrics, WebSocket behavior | database fallback and cache reconnection |
| Redpanda | stop broker | fail-open publish logs, outbox age | broker recovery and controlled republish |
| Notification provider | timeout/5xx stub | notification result, breaker, incident retained | later bounded attempt without duplicate incident |
| Inference/LLM | timeout/invalid response | agent state, resilience metrics | deterministic incident guidance remains usable |

The executable resilience exercise is
[`verify-resilience-fault.sh`](../../scripts/verify-resilience-fault.sh); keep its invocation and
failure-injection details in the script rather than duplicating them here.

Measure **time to detection**, **time to containment**, **time to recovery**, and whether queued or
retried work drains safely. Merely observing an exception is not recovery evidence.

For the PostgreSQL exercise, start a disposable core stack, then run
`just --justfile just/labs.just lab-chaos`. The lab requires `/readyz` to become non-200 while
PostgreSQL is stopped, then waits for both `pg_isready` and `/readyz` after restart. Its exit cleanup
restarts the database if the exercise fails. Follow it with the focused incident API integration test.
This is opt-in local fault evidence, not a production recovery claim.

## 10x and 100x Review

At 10x, identify the first measured bottleneck and prefer bounds, query/index tuning, batching,
retention, and stateless replicas. At 100x, revisit workload separation, partition ownership,
broker lag, telemetry cost, database availability, and cross-tenant fairness. Record why sharding,
Kubernetes, a managed gateway, or another database is still unnecessary—or which measurement now
justifies it.
