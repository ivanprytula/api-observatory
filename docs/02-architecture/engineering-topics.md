# Evergreen Engineering Topics

This is the canonical lookup index for backend, distributed-systems, platform, security, and
reliable-AI concepts demonstrated by API Observatory. It answers **where a topic lives and how
strong the evidence is**; linked code, tests, ADRs, and runbooks remain the detailed sources.

## Evidence Status

| Status | Meaning |
| --- | --- |
| **Core** | Implemented in the application path and covered by focused tests. |
| **Lab** | Executable or configurable in an isolated/local environment, not a production claim. |
| **Decision** | Analyzed as an architecture/deployment choice; not exercised as a live production system. |
| **Deferred** | Deliberately postponed until a measurable trigger justifies the complexity. |
| **Historical** | Useful background from an older design, not evidence of current behavior. |

Agents must verify linked evidence in the current checkout before answering. Files under
`docs/_archive/` can explain history but cannot upgrade a topic's status.

## Ownership Levels

| Level | Expected capability |
| --- | --- |
| **Locate** | Find current implementation, tests, configuration, and documentation. |
| **Explain** | Describe behavior, data flow, failure modes, and tradeoffs. |
| **Operate** | Test, diagnose, measure, recover, migrate, and roll back. |
| **Lead** | Set adoption triggers, sequence change safely, and defend the decision. |

## Topic Map

| # | Topic | Status | Strongest current evidence |
| ---: | --- | --- | --- |
| 1 | API contracts, validation, and versioning | Core | Shared Pydantic contracts plus OpenAPI auth-contract tests |
| 2 | Authentication, authorization, multi-tenancy, and RLS | Core | JWT/API-key guards, tenant context, PostgreSQL RLS tests |
| 3 | API gateways and reverse proxies | Lab | Opt-in nginx edge profile and gateway smoke test |
| 4 | Rate limiting, abuse prevention, and SSRF | Core | Tenant/subject token bucket, abuse signals, URL validation |
| 5 | Schema design, constraints, and migrations | Core | SQLAlchemy models, Alembic migrations, schema integrity tests |
| 6 | Transactions, isolation, locking, and concurrency | Core | Async repositories, RLS/locking/concurrency integration tests |
| 7 | Indexing, query plans, and database performance | Core | Query-analysis/performance tests and scorecard SQL aggregation |
| 8 | Partitioning, replication, and sharding | Deferred | Archive partitioning is real; cross-node sharding is not |
| 9 | Retention, archival, and data lifecycle | Core | Bounded archive-before-delete lifecycle and integration tests |
| 10 | Caching and invalidation | Core | Scorecard cache, invalidation, warming, and fallback tests |
| 11 | Async I/O, concurrency limits, and backpressure | Core | Async HTTP/DB paths and bounded dependency resilience |
| 12 | Kafka partitioning, consumer groups, and delivery semantics | Core + Lab | Producer is active; consumer-group behavior still needs an isolated executable lab |
| 13 | Idempotency and outbox/inbox patterns | Core | Persisted outbox/inbox schema and lifecycle tests |
| 14 | Timeouts, retries, circuit breakers, and bulkheads | Core | Shared resilience primitives and fault-verification script |
| 15 | Dead-letter queues and replay | Core + Decision | Persisted DLQ state exists; end-to-end Kafka routing/replay is not exercised |
| 16 | Scheduling, distributed locks, and leader coordination | Core | APScheduler registry, Redis lock, scheduler tests |
| 17 | Load balancing and autoscaling | Lab | Local ingress, replicas, HPA, and service configuration |
| 18 | Health checks, observability, SLOs, and incident response | Core | Health/readiness, telemetry, and tenant-safe dependency incidents |
| 19 | IaC, deployment, rollback, and zero-downtime change | Decision | Local sandboxes plus unexecuted AWS Stage 0 contract |
| 20 | Reliable AI/RAG, human review, and evaluation | Core | LangGraph HITL flow and deterministic offline evaluation |

## 1. API Contracts, Validation, and Versioning

- **Problem:** prevent incompatible request, response, and cross-service event changes.
- **Status:** **Core**. **Ownership target:** Explain.
- **Where:** [shared schemas](../../libs/contracts/schemas.py), [event contracts](../../libs/contracts/events.py),
  [contract version](../../libs/contracts/VERSION), [OpenAPI contract test](../../services/ingestor/tests/contract/test_openapi_auth_contract.py),
  and [contract changelog](../../libs/contracts/CHANGELOG.md).
- **Behavior:** FastAPI/Pydantic validate API boundaries; shared contracts are explicitly versioned and
  service-boundary imports are checked in CI.
- **Proof:** `uv run pytest services/ingestor/tests/contract/test_openapi_auth_contract.py -q`
- **Failure/operations:** schema drift or an unguarded route appears as a contract-test failure; incompatible
  event changes risk mixed-version consumers.
- **Tradeoff:** a small shared contract library keeps one source of truth; independent generated clients and
  a schema registry are deferred.
- **Scale trigger:** independently released consumers or multiple external client teams require compatibility
  gates and formal deprecation windows.
- **At 10x/100x:** traffic does not change the contract mechanism; organizational/release independence does.
- **Interview check:** How would you roll out a required response field without breaking an older client?
- **Last verified:** 2026-07-24.

## 2. Authentication, Authorization, Multi-Tenancy, and RLS

- **Problem:** establish identity and prevent cross-tenant object access.
- **Status:** **Core**. **Ownership target:** Operate.
- **Where:** [auth helpers](../../services/ingestor/auth.py), [authorization policy](../../services/ingestor/security/authorization.py),
  [tenant context](../../services/ingestor/core/tenant.py), [API keys](../../services/ingestor/security/api_keys.py),
  [RLS migration](../../alembic/versions/20260723_190000_enable_observations_rls.py), and
  [RLS tests](../../tests/test_rls.py).
- **Behavior:** JWT/API-key identity feeds explicit role and tenant checks; observations can add a PostgreSQL
  RLS enforcement layer behind a feature flag.
- **Proof:** `uv run pytest services/ingestor/tests/unit/auth tests/test_rls.py -q`
- **Failure/operations:** missing tenant assignment must fail closed; auth-demo routes are opt-in and must not
  be confused with the production v1 surface.
- **Tradeoff:** application filtering plus incremental RLS avoids an unsafe all-tables migration.
- **Scale trigger:** new tenant-owned tables require table-by-table access-pattern verification before RLS.
- **At 10x/100x:** add identity-provider/OIDC integration, policy audit tooling, and connection-pool-aware RLS
  validation; do not weaken object authorization for throughput.
- **Interview check:** Why is endpoint authentication insufficient for tenant isolation?
- **Last verified:** 2026-07-24.

## 3. API Gateways and Reverse Proxies

- **Problem:** centralize ingress, TLS termination, routing, and edge policy.
- **Status:** **Lab**. **Ownership target:** Explain.
- **Where:** [nginx configuration](../../infra/nginx/nginx.conf), [Compose ingress profile](../../docker-compose.yml),
  [Kubernetes ingress](../../infra/kubernetes/overlays/local/ingress.yaml), and
  [isolated gateway lab](../../labs/gateway_load_balancing/README.md).
- **Behavior:** nginx/local ingress forwards traffic and adds edge controls; it is not evidence of a managed API
  gateway with per-consumer products, transformations, billing, or a production control plane.
- **Proof:** run the isolated lab and `uv run python labs/gateway_load_balancing/verify_distribution.py`.
- **Failure/operations:** bad upstream health, timeout, forwarded-header, or TLS configuration can make a healthy
  app unreachable.
- **Tradeoff:** a reverse proxy is sufficient for the playground; a managed gateway would add cost and policy
  duplication without current consumers.
- **Scale trigger:** multiple public services, distinct consumer quotas, external developer onboarding, or edge
  authentication policies.
- **At 10x/100x:** tune connection reuse and limits first; adopt managed/global ingress only when availability
  and regional routing requirements appear.
- **Interview check:** Which responsibilities belong in a gateway, and which must remain in the service?
- **Last verified:** 2026-07-24.

## 4. Rate Limiting, Abuse Prevention, and SSRF

- **Problem:** protect finite capacity and prevent server-side requests to unsafe networks.
- **Status:** **Core**. **Ownership target:** Operate.
- **Where:** [token bucket](../../services/ingestor/rate_limiting_token_bucket.py),
  [abuse detection](../../services/ingestor/security/abuse_detection.py),
  [source URL validation](../../services/ingestor/repositories/source_registry.py), and
  [rate-limit tests](../../services/ingestor/tests/integration/observations/test_v2_rate_limiting.py).
- **Behavior:** production v1 keys rate limits by tenant and subject; outbound source URLs are resolved and checked
  against unsafe address ranges before use.
- **Proof:** `uv run pytest services/ingestor/tests/unit/observations/test_rate_limiting.py tests/unit/test_abuse_detection_detectors.py -q`
- **Failure/operations:** cache loss changes enforcement behavior; DNS rebinding and redirect targets remain part
  of SSRF threat analysis.
- **Tradeoff:** Redis provides shared atomic state, with constrained local fallback for development.
- **Scale trigger:** multi-region traffic or contractual quotas require globally coordinated or gateway-assisted
  enforcement.
- **At 10x/100x:** reduce hot-key contention, partition counters, and separate protection limits from billable
  product quotas.
- **Interview check:** Why are a semaphore, a rate limiter, and backpressure not interchangeable?
- **Last verified:** 2026-07-24.

## 5. Schema Design, Constraints, and Migrations

- **Problem:** preserve data invariants while evolving a live schema safely.
- **Status:** **Core**. **Ownership target:** Operate.
- **Where:** [ORM models](../../services/ingestor/models.py), [Alembic migrations](../../alembic/versions/),
  [schema integrity tests](../../tests/integration/schema/test_schema_integrity.py), and
  [migration ADR](adr/007-migration-runner-vs-sidecar.md).
- **Behavior:** SQLAlchemy 2.0 models declare constraints/indexes; Alembic is the schema source of truth and tests
  verify important database objects.
- **Proof:** `uv run pytest tests/integration/schema/test_schema_integrity.py -q`
- **Failure/operations:** model/migration drift, long locks, and non-backward-compatible deploy order are the main
  risks.
- **Tradeoff:** one migration chain is operationally simpler than per-feature schema ownership at this scale.
- **Scale trigger:** independent deployables with separate data ownership justify per-service migration pipelines.
- **At 10x/100x:** prefer expand/migrate/contract changes, online index creation, bounded backfills, and measured
  lock budgets.
- **Interview check:** How do you safely make a nullable column required on a large table?
- **Last verified:** 2026-07-24.

## 6. Transactions, Isolation, Locking, and Concurrency

- **Problem:** preserve invariants when requests and workers modify shared state concurrently.
- **Status:** **Core**. **Ownership target:** Operate.
- **Where:** [database setup](../../services/ingestor/database.py), [observation repository](../../services/ingestor/repositories/observations.py),
  [messaging repository](../../services/ingestor/repositories/messaging.py), and
  [concurrency tests](../../services/ingestor/tests/integration/observations/test_concurrency.py).
- **Behavior:** async sessions define transaction boundaries; uniqueness, row locks, and idempotent operations
  handle concurrent work without relying on process-local state.
- **Proof:** `uv run pytest services/ingestor/tests/integration/observations/test_concurrency.py tests/integration/schema/test_outbox_inbox_baseline.py -q`
- **Failure/operations:** lost updates, deadlocks, long transactions, and connection-pool exhaustion require
  distinct diagnosis.
- **Tradeoff:** default PostgreSQL isolation plus explicit locks/constraints is simpler than globally stronger
  isolation.
- **Scale trigger:** observed anomalies or multi-step financial-like invariants justify stricter isolation or
  serialized workflows.
- **At 10x/100x:** shorten transactions, bound lock waits, partition hot records, and measure pool/DB saturation.
- **Interview check:** When is a unique constraint better than an application-level existence check?
- **Last verified:** 2026-07-24.

## 7. Indexing, Query Plans, and Database Performance

- **Problem:** keep query latency and database work bounded as data grows.
- **Status:** **Core**. **Ownership target:** Operate.
- **Where:** [scorecard repository](../../services/ingestor/repositories/scorecards.py),
  [query-analysis tests](../../services/ingestor/tests/integration/observations/test_query_analysis.py),
  [performance tests](../../services/ingestor/tests/integration/observations/test_performance.py), and
  [schema indexes](../../services/ingestor/models.py).
- **Behavior:** PostgreSQL performs percentile/aggregate work; indexes reflect current access patterns and are
  evaluated with query-plan evidence rather than added speculatively.
- **Proof:** run the PostgreSQL integration profile for `test_query_analysis.py` and capture
  `EXPLAIN (ANALYZE, BUFFERS)` for the chosen scorecard query.
- **Failure/operations:** sequential scans are not automatically wrong; stale statistics, low selectivity, write
  amplification, and cache effects matter.
- **Tradeoff:** keep analytical SQL close to PostgreSQL instead of copying rows into Python.
- **Scale trigger:** measured latency/IO/SLO breach after query and index tuning justifies precomputation or a
  read model.
- **At 10x/100x:** consider materialization, incremental aggregation, replicas, or analytical storage only after
  measuring the dominant workload.
- **Interview check:** How do you prove that a new index helps overall rather than one query in isolation?
- **Last verified:** 2026-07-24.

## 8. Partitioning, Replication, and Sharding

- **Problem:** distribute storage or work when one table/node/partition no longer meets requirements.
- **Status:** **Deferred** for cross-node database sharding; **Lab** for table/Kafka partitioning models.
  **Ownership target:** Explain.
- **Where:** [archive migration](../../alembic/versions/20260723_170000_add_observations_archive.py),
  [partition tests](../../services/ingestor/tests/integration/observations/test_materialized_views_and_partitioning.py),
  [partition/sharding lab](../../labs/partitioning_sharding/README.md), and [Kafka ADR](adr/001-kafka-vs-rabbitmq.md).
- **Behavior:** observations move into an archive table; isolated tests/labs demonstrate table partitioning and
  keyed Kafka routing. None of these is equivalent to a sharded PostgreSQL cluster.
- **Proof:** `uv run pytest tests/unit/test_evergreen_labs.py -q`, then run the isolated real-broker experiment.
- **Failure/operations:** poor shard keys create hotspots; resharding and cross-shard transactions are operational
  costs absent from table partitioning.
- **Tradeoff:** a single PostgreSQL authority keeps joins, constraints, backups, and consistency simple.
- **Scale trigger:** a measured single-node storage/write/availability limit that vertical tuning, partitioning,
  archiving, and replicas cannot meet.
- **At 10x/100x:** 10x favors retention, indexes, partitioning, and replicas; 100x may justify tenant/source-based
  shards only with routing, rebalancing, and recovery designs.
- **Interview check:** Contrast table partitioning, read replicas, Kafka partitions, and database sharding.
- **Last verified:** 2026-07-24.

## 9. Retention, Archival, and Data Lifecycle

- **Problem:** bound hot storage while preserving verifiable historical data.
- **Status:** **Core**. **Ownership target:** Operate.
- **Where:** [retention job](../../services/ingestor/jobs.py), [retention runner](../../scripts/run-retention.py),
  [archive migration](../../alembic/versions/20260723_170000_add_observations_archive.py), and
  [retention tests](../../services/ingestor/tests/integration/test_retention.py).
- **Behavior:** a disabled-by-default, bounded job copies and verifies eligible observations before deleting the
  corresponding hot rows.
- **Proof:** `uv run pytest services/ingestor/tests/unit/core/test_retention.py services/ingestor/tests/integration/test_retention.py -q`
- **Failure/operations:** partial copies, incorrect event-time boundaries, large transactions, and reruns must not
  lose or duplicate data.
- **Tradeoff:** manual invocation and PostgreSQL archive storage minimize operational scope for the current scale.
- **Scale trigger:** sustained volume/cost or retention requirements justify native partition drops and object
  storage.
- **At 10x/100x:** increase bounded cadence first; later use partition lifecycle and independently verified cold
  storage.
- **Interview check:** Why must archival be verified before deletion, and how is a retry made safe?
- **Last verified:** 2026-07-24.

## 10. Caching and Invalidation

- **Problem:** avoid repeated expensive reads without returning stale or cross-tenant data.
- **Status:** **Core**. **Ownership target:** Operate.
- **Where:** [cache module](../../services/ingestor/cache.py), [scorecard cache tests](../../services/ingestor/tests/integration/observations/test_cache.py),
  [warming tests](../../services/ingestor/tests/unit/test_cache_warming.py), and
  [cache verification script](../../scripts/testing/02-verify-cache-layer.sh).
- **Behavior:** Redis-backed scorecard caching uses bounded TTL/invalidation and preserves a database fallback when
  caching is disabled.
- **Proof:** `uv run pytest services/ingestor/tests/unit/test_cache_list.py services/ingestor/tests/unit/test_cache_warming.py -q`
- **Failure/operations:** stale values, stampedes, serialization drift, key collisions, and Redis loss are separate
  risks.
- **Tradeoff:** cache only measured read paths; PostgreSQL remains the source of truth.
- **Scale trigger:** cache-miss database saturation or latency SLO evidence justifies broader caching/tiering.
- **At 10x/100x:** add request coalescing, jittered TTLs, key partitioning, capacity policies, and regional
  consistency decisions.
- **Interview check:** What invalidates a scorecard, and what happens when invalidation fails?
- **Last verified:** 2026-07-24.

## 11. Async I/O, Concurrency Limits, and Backpressure

- **Problem:** handle many I/O waits without blocking the event loop or accepting unbounded work.
- **Status:** **Core**. **Ownership target:** Operate.
- **Where:** [source probes](../../services/ingestor/jobs.py), [dependency resilience](../../libs/platform/resilience.py),
  [bulkhead](../../libs/platform/bulkhead.py), and [resilience tests](../../tests/unit/test_dependency_resilience.py).
- **Behavior:** FastAPI, HTTP, Redis, Kafka, and SQL paths are async; shared dependency wrappers bound concurrent
  calls and queued work.
- **Proof:** `uv run pytest tests/unit/test_dependency_resilience.py services/ingestor/tests/unit/core/test_bulkhead_retry_budget.py -q`
- **Failure/operations:** blocking calls, orphan tasks, cancellation leaks, queue growth, and downstream saturation
  can all present as latency.
- **Tradeoff:** cooperative async is appropriate for I/O-bound work; CPU-heavy work belongs outside the event loop.
- **Scale trigger:** event-loop lag, saturated dependency limits, or CPU profiles justify worker/process changes.
- **At 10x/100x:** first bound/admit work and scale stateless consumers; later separate independently scaling CPU or
  queue workloads.
- **Interview check:** How do backpressure and load shedding protect recovery time?
- **Last verified:** 2026-07-24.

## 12. Kafka Partitioning, Consumer Groups, and Delivery Semantics

- **Problem:** move durable events between independently processing components with controlled ordering.
- **Status:** **Core** for producer integration; **Lab** for consumer groups and partition scaling.
  **Ownership target:** Explain.
- **Where:** [Kafka producer](../../services/ingestor/events.py),
  [persisted event state](../../services/ingestor/storage/events.py), [event contracts](../../libs/contracts/events.py),
  [consumer-group lab](../../labs/partitioning_sharding/kafka_partition_demo.py), and
  [broker ADR](adr/001-kafka-vs-rabbitmq.md).
- **Behavior:** Redpanda exposes the Kafka protocol locally and the ingestor has a fail-open producer. Persisted
  event metadata models offsets, retries, and failure state. The isolated lab exercises stable key routing and a
  temporary consumer group, but the application has no always-on standalone consumer.
- **Proof:** run `labs/partitioning_sharding/kafka_partition_demo.py` against its isolated broker and
  `uv run pytest services/ingestor/tests/integration/storage/test_events_idempotency.py -q`.
- **Failure/operations:** rebalance, poison messages, lag, ordering scope, and publish/commit gaps require explicit
  handling.
- **Tradeoff:** Kafka semantics provide a useful event-log learning surface; simpler queues would be cheaper for
  many small workloads.
- **Scale trigger:** sustained asynchronous fan-out, replay, or per-key ordering requirements justify broker cost.
- **At 10x/100x:** increase partitions with a stable key, then consumers; monitor skew and rebalance behavior before
  adding clusters.
- **Interview check:** What delivery guarantee does this consumer actually achieve, and where can duplicates occur?
- **Last verified:** 2026-07-24.

## 13. Idempotency and Outbox/Inbox Patterns

- **Problem:** make retries and at-least-once delivery safe across database and broker boundaries.
- **Status:** **Core**. **Ownership target:** Operate.
- **Where:** [outbox/inbox models](../../services/ingestor/models.py),
  [messaging repository](../../services/ingestor/repositories/messaging.py), and
  [lifecycle tests](../../tests/integration/schema/test_outbox_inbox_baseline.py).
- **Behavior:** unique idempotency/message keys reject duplicates; pending outbox rows are claimable, retryable, and
  marked published; inbox rows deduplicate consumers.
- **Proof:** `uv run pytest tests/integration/schema/test_outbox_inbox_baseline.py -q`
- **Failure/operations:** a table alone is not end-to-end delivery; publisher scheduling, stuck claims, retry age,
  and consumer transaction boundaries must be observed.
- **Tradeoff:** PostgreSQL-backed coordination avoids distributed transactions and another durable coordinator.
- **Scale trigger:** outbox lag or write amplification beyond database capacity justifies CDC/log-based publishing.
- **At 10x/100x:** batch claims and partition ownership first; later consider CDC with explicit ordering and replay
  migration.
- **Interview check:** Why can “write DB, then publish” lose events even when both calls usually succeed?
- **Last verified:** 2026-07-24.

## 14. Timeouts, Retries, Circuit Breakers, and Bulkheads

- **Problem:** keep one slow or failing dependency from consuming all service capacity.
- **Status:** **Core**. **Ownership target:** Operate.
- **Where:** [resilience facade](../../libs/platform/resilience.py), [circuit breaker](../../libs/platform/circuit_breaker.py),
  [retry policy](../../libs/platform/retry.py), [HTTP timeout](../../libs/platform/http_timeout.py), and
  [fault script](../../scripts/verify-resilience-fault.sh).
- **Behavior:** outbound work has time bounds, retry budgets, concurrency/queue limits, and breaker state with
  telemetry.
- **Proof:** `uv run pytest tests/test_circuit_breaker.py tests/unit/test_dependency_resilience.py tests/unit/test_request_timeout.py -q`
- **Failure/operations:** retry storms, non-idempotent retries, half-open races, and overly broad circuit scope can
  worsen incidents.
- **Tradeoff:** shared small primitives keep policies explicit; dependency-specific behavior still belongs near the
  call site.
- **Scale trigger:** multiple services and policy drift justify centralized libraries/configuration, not one global
  breaker.
- **At 10x/100x:** use adaptive admission/load shedding and per-tenant fairness before simply increasing limits.
- **Interview check:** Which errors are retryable, and how do timeout and retry budgets compose?
- **Last verified:** 2026-07-24.

## 15. Dead-Letter Queues and Replay

- **Problem:** isolate poison events without blocking healthy partition progress and support controlled recovery.
- **Status:** **Core** for persisted failure state; **Decision** for end-to-end Kafka routing and replay.
  **Ownership target:** Operate.
- **Where:** [event failure repository](../../services/ingestor/storage/events.py), [processed-event model](../../services/ingestor/models.py),
  and the canonical [DLQ replay runbook](https://github.com/ivanprytula/api-observatory-infra/blob/main/docs/operations/runbooks/dlq-replay.md).
- **Behavior:** processed events can be marked as dead-lettered with failure metadata. The repository does not yet
  prove a running consumer that retries, publishes to a Kafka DLQ topic, and safely replays it.
- **Proof:** run the focused consumer/idempotency tests, then use the runbook against the opt-in local broker.
- **Failure/operations:** blind replay can recreate load spikes or repeat permanent failures; replay must preserve
  identity and rate limits.
- **Tradeoff:** a separate DLQ keeps the main stream moving while retaining failed inputs for operator control.
- **Scale trigger:** high DLQ volume requires classification, quarantine tooling, ownership, and replay SLOs.
- **At 10x/100x:** partition DLQs by domain/severity and automate only validated transient categories.
- **Interview check:** What evidence is required before replaying a poison message?
- **Last verified:** 2026-07-24.

## 16. Scheduling, Distributed Locks, and Leader Coordination

- **Problem:** run periodic work once when application processes or replicas overlap.
- **Status:** **Core** for scheduling/locks; multi-replica leader election remains unproven. **Ownership target:** Explain.
- **Where:** [job registry](../../services/ingestor/jobs_registry.py), [jobs](../../services/ingestor/jobs.py),
  [Redis lock](../../services/ingestor/cache.py), and [scheduler tests](../../services/ingestor/tests/integration/test_scheduler.py).
- **Behavior:** APScheduler registers source jobs; selected work uses Redis coordination, but horizontal API scaling
  must account for scheduler ownership explicitly.
- **Proof:** `uv run pytest services/ingestor/tests/integration/test_scheduler.py services/ingestor/tests/unit/test_redis_lock.py -q`
- **Failure/operations:** duplicate schedulers, expired leases, clock assumptions, and long-running work can produce
  overlaps.
- **Tradeoff:** in-process scheduling is operationally simple for the current single active scheduler.
- **Scale trigger:** multiple always-on replicas or independent job SLOs justify a dedicated scheduler/worker or
  leader-election design.
- **At 10x/100x:** separate API serving from scheduling, shard jobs deterministically, and make every handler
  idempotent.
- **Interview check:** What happens if two replicas register the same interval job?
- **Last verified:** 2026-07-24.

## 17. Load Balancing and Autoscaling

- **Problem:** distribute requests and replace unhealthy capacity without exposing instance identity.
- **Status:** **Lab**. **Ownership target:** Explain.
- **Where:** [Kubernetes service](../../infra/kubernetes/overlays/local/ingestor-service.yaml),
  [replicas](../../infra/kubernetes/overlays/local/ingestor-deployment.yaml),
  [HPA](../../infra/kubernetes/overlays/local/ingestor-hpa.yaml), and
  [gateway/load-balancing lab](../../labs/gateway_load_balancing/README.md).
- **Behavior:** the isolated lab distributes requests across three stateless replicas and exercises passive health
  removal/recovery; Kubernetes manifests describe replicas/HPA but no production autoscaling event is claimed.
- **Proof:** run the standalone lab verifier, stop one replica, verify recovery, restart it, and tear the lab down.
- **Failure/operations:** readiness, sticky local state, WebSockets, connection pools, and the in-process scheduler
  complicate horizontal scaling.
- **Tradeoff:** single-instance Stage 0 remains easier to operate; Kubernetes artifacts are an opt-in learning path.
- **Scale trigger:** measured saturation plus a stateless/request-safe application path and an availability target
  that needs multiple instances.
- **At 10x/100x:** 10x may need more stateless replicas and pool tuning; 100x needs workload separation, partition
  planning, and multi-zone failure analysis.
- **Interview check:** Why can adding API replicas duplicate background jobs even if HTTP is stateless?
- **Last verified:** 2026-07-24.

## 18. Health Checks, Observability, SLOs, and Incident Response

- **Problem:** detect, explain, and recover from degraded behavior using service-level evidence.
- **Status:** **Core**. **Ownership target:** Operate.
- **Where:** [health routes](../../services/ingestor/routers/health_ingestion_jobs.py),
  [metrics](../../services/ingestor/metrics.py), [tracing](../../libs/platform/tracing.py),
  [Prometheus rules](../../infra/monitoring/rules/alert.local.rules.yml), and
  [incident lifecycle](../08-operations/dependency-incidents.md).
- **Behavior:** liveness/readiness and telemetry support diagnosis; repeated availability/latency failures and
  breaking drift create deduplicated tenant-scoped incidents with acknowledgement, recovery, cooldown, guidance,
  notifications, metrics, and dashboard visibility.
- **Proof:** `uv run pytest services/ingestor/tests/unit/core/test_incident_lifecycle.py services/ingestor/tests/integration/test_incidents_api.py services/ingestor/tests/integration/test_contract_drift_api.py -q`
- **Failure/operations:** missing correlation, high-cardinality labels, incorrect readiness, and alerts without an
  owner make telemetry ineffective.
- **Tradeoff:** open-source local components maximize learning and reproducibility; managed operations are not
  claimed.
- **Scale trigger:** real on-call/SLO obligations justify managed retention, paging, ownership, and error budgets.
- **At 10x/100x:** control telemetry cardinality/sampling/cost and preserve end-to-end correlation across services.
- **Interview check:** What is the difference between liveness, readiness, an SLI, and an SLO?
- **Last verified:** 2026-07-24.

## 19. IaC, Deployment Strategies, Rollback, and Zero-Downtime Change

- **Problem:** make environments and releases reviewable, reproducible, and recoverable.
- **Status:** **Decision** for real AWS Stage 0; local sandbox/config validation is executable. **Ownership target:** Explain.
- **Where:** [AWS service contract](../../infra/deployment/aws-stage0-services.json),
  [contract validator](../../scripts/validate_aws_deployment_contract.py),
  [deployment contract](../07-deployment/app-repo-contract.md), and the sibling infra repository's Terraform,
  Ansible, and CI sources.
- **Behavior:** the app publishes a machine-readable service contract; the infra repo owns real cloud resources and
  runtime delivery. This checkout is not evidence of a completed cloud deployment.
- **Proof:** `uv run pytest tests/unit/test_aws_deployment_contract.py -q` and run Terraform plan/validation only in
  the documented sandbox or approved real environment.
- **Failure/operations:** schema/image/config ordering, health gates, immutable tags, secret delivery, and rollback
  compatibility define safe rollout.
- **Tradeoff:** EC2 plus Compose is the low-complexity Stage 0 target; ECS/Kubernetes require demonstrated needs.
- **Scale trigger:** availability, independent scaling, or deploy-frequency evidence justifies the next stage.
- **At 10x/100x:** automate progressive health gates and workload separation; multi-region adds data-consistency and
  failover problems, not just more compute.
- **Interview check:** How do expand/contract migrations interact with application rollback?
- **Last verified:** 2026-07-24.

## 20. Reliable AI/RAG, Human Review, and Evaluation

- **Problem:** make nondeterministic analysis bounded, inspectable, optional, and quality-checked.
- **Status:** **Core** for the local/optional agent path and offline evaluation. **Ownership target:** Explain.
- **Where:** [LangGraph graph](../../services/ingestor/agent/graph.py), [nodes](../../services/ingestor/agent/nodes.py),
  [runner](../../services/ingestor/agent/runner.py), [evaluation](../../services/ingestor/agent/evals/evaluator.py),
  and [agent ADR](adr/012-langgraph-agent.md).
- **Behavior:** critical/breaking drift can trigger a checkpointed graph that classifies, retrieves context, drafts
  structured analysis, pauses for human review, and notifies after approval; deterministic fixtures evaluate
  recorded outputs without provider access.
- **Proof:** `uv run pytest services/ingestor/tests/unit/agent services/ingestor/tests/integration/test_agent_router.py -q`
  and `uv run python scripts/eval/run-agent-eval.py --output /tmp/agent-eval-report.json`.
- **Failure/operations:** provider absence, invalid structured output, retrieval failure, checkpoint recovery, cost,
  and unsafe automation are explicit boundaries.
- **Tradeoff:** AI is fail-open and human-reviewed; deterministic incident handling must not depend on a model.
- **Scale trigger:** measured quality and workload justify semantic/LLM-as-judge evaluation, caching, routing, and
  cost controls.
- **At 10x/100x:** enforce concurrency/rate/cost budgets, version prompts and datasets, and separate evaluation from
  production feedback loops.
- **Interview check:** How do you evaluate an agent when the provider output is nondeterministic?
- **Last verified:** 2026-07-24.

## Maintenance Protocol

When code or architecture changes touch a listed topic:

1. Verify the linked source and proof command.
2. Update status only when evidence crosses a boundary.
3. Keep future-scale designs as **Deferred** until their trigger is measured.
4. Add a new topic only when it is evergreen and not already covered by an existing entry.
5. Review ownership targets quarterly; catalogue breadth alone is not expertise.
