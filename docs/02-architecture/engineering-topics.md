# Evergreen Engineering Evidence

This is the compact map from an engineering topic to current repository proof. It is not a
tutorial: open the linked implementation and tests, run the focused proof, and use the adoption
trigger to explain why the design should or should not change.

## Evidence Status

- **Core:** implemented and tested in the application path.
- **Lab:** executable in an isolated local environment.
- **Decision:** documented/configured but not exercised as production behavior.
- **Deferred:** waits for a measurable trigger.
- **Historical:** retained only to explain an older choice.

## Topic Map

| Topic | Status | Primary evidence | Adoption or change trigger |
| --- | --- | --- | --- |
| API contracts and versioning | **Core** | [`libs/contracts`](../../libs/contracts/), [contract tests](../../services/ingestor/tests/contract/) | A cross-process schema change requires a version bump and compatibility plan |
| Authentication, authorization, tenancy, RLS | **Core** | [security architecture](security-architecture.md), [`security/`](../../services/ingestor/security/), [observation RLS tests](../../services/ingestor/tests/integration/test_observations_rls.py), [incident RLS tests](../../services/ingestor/tests/integration/test_dependency_incidents_rls.py) | Extend RLS table-by-table after each access path is verified |
| Gateway and reverse proxy | **Lab** | [gateway lab](../../labs/gateway_load_balancing/), local edge profile | Adopt a managed gateway for multiple public services or consumer-specific edge policy |
| Rate limiting and SSRF | **Core** | [`rate_limiting.py`](../../services/ingestor/rate_limiting.py) (slowapi, edge), [`rate_limiting_token_bucket.py`](../../services/ingestor/rate_limiting_token_bucket.py) (token bucket, authenticated routes) | Two mechanisms serve different layers: slowapi for unauthenticated health/version endpoints; token bucket for authenticated v1 routes requiring distributed Redis enforcement |
| Schema design and migrations | **Core** | [`models/`](../../services/ingestor/models/), [`alembic/`](../../alembic/) | Split migration ownership only with independently deployed data owners |
| Transactions and concurrency | **Core** | [repositories](../../services/ingestor/repositories/), [concurrency tests](../../services/ingestor/tests/integration/observations/test_concurrency.py) | Add stronger coordination after measured contention or multi-writer conflicts |
| Indexing and query performance | **Core** | migrations, scorecard SQL, [performance worksheet](../05-development/performance-and-failure-lab.md) | Change indexes from captured query plans and representative workloads |
| Partitioning, replication, sharding | **Lab / Deferred** | [partitioning lab](../../labs/partitioning_sharding/) | A measured single-node limit remains after query, index, and retention work |
| Retention and archival | **Core** | `just retention-dry-run`, [retention tests](../../services/ingestor/tests/integration/test_retention.py) | Add partition/cold storage when bounded batches cannot meet retention SLOs |
| Caching and invalidation | **Core** | cache modules and tests under [`services/ingestor`](../../services/ingestor/) | Add cache tiers only after measured latency/load and an explicit invalidation rule |
| Async I/O and backpressure | **Core** | [`libs/platform`](../../libs/platform/), background-worker tests | Separate workers when queue latency or API isolation needs independent scaling |
| Kafka partitions and consumer groups | **Lab / Core seam** | [Kafka lab](../../labs/partitioning_sharding/), broker code under `services/ingestor` | Operate managed Kafka only for a real asynchronous workload and delivery objective |
| Idempotency and outbox/inbox | **Core** | [`storage/events.py`](../../services/ingestor/storage/events.py), [event tests](../../services/ingestor/tests/integration/storage/) | Add CDC only when polling/claim throughput or ownership demands it |
| Timeouts, retries, breakers, bulkheads | **Core** | [`libs/platform`](../../libs/platform/), [`just --justfile just/labs.just lab-resilience-fault`](../../just/labs.just) | Tune or externalize controls from measured dependency failures |
| DLQ and replay | **Core seam / Lab operation** | broker implementation, infra recovery guide | Add quarantine tooling when DLQ volume or replay risk exceeds manual bounded recovery |
| Scheduling and locks | **Core** | [`jobs/`](../../services/ingestor/jobs/), scheduler tests | Single-instance APScheduler is a conscious design constraint for current scale; extract scheduler ownership before running multiple ingestor replicas |
| Load balancing and autoscaling | **Lab / Deferred** | [gateway lab](../../labs/gateway_load_balancing/), local HPA manifests | Require saturation/availability evidence and a stateless request path |
| Health, observability, SLOs, incidents | **Core / Lab stack** | [observability](../08-operations/observability.md), [dependency incidents](../08-operations/dependency-incidents.md) | Managed paging/retention follows a real on-call or SLO obligation |
| WebSocket / real-time push | **Lab** | [`routers/ws.py`](../../services/ingestor/routers/ws.py), [WebSocket tests](../../services/ingestor/tests/integration/observations/test_ws.py) | Adopt only when a real-time dashboard client requires live event streaming |
| IaC, deployment, rollback | **Decision** | [deployment contract](../07-deployment/app-repo-contract.md), infra guide | Real cloud evidence requires approved provisioning, verification, rollback, and teardown |
| AI/RAG and evaluation | **Core optional path** | [`agent/`](../../services/ingestor/agent/), [`evals/`](../../services/ingestor/agent/evals/), [eval design](agent-evals.md) | Provider-backed evaluation or more autonomy requires measured value and human-review safety |

## Proof Route

For any topic:

1. Locate the linked implementation and focused test.
2. Explain the data/dependency boundary and failure behavior.
3. Run the smallest applicable proof from [development workflows](../05-development/dev-workflows.md)
   or the [performance/failure worksheet](../05-development/performance-and-failure-lab.md).
4. State what is not proven and which measurement would justify a new design.

Update a row only when its status, primary proof, or adoption trigger changes. Detailed behavior
belongs in code, tests, ADRs, or the owning operational document.
