# Technology Choice Decision Trees

Track: C — Architecture and Platform Strategy

No code — these are the "why" answers. Use Ctrl+F to jump to any topic.

---

## How to Use

Each entry follows this structure:

```text
Choose X when: [conditions]
Trade-off: [what you give up]
Interview answer: [1-3 sentences you can say out loud]
```

---

## Core Language & Runtime

### Async vs Sync Python

**Choose async when:** your bottleneck is I/O — database queries, HTTP calls, file reads. Every `await` yields the event loop, letting other requests run while you wait. One process handles hundreds of concurrent requests.

**Choose sync (threads/multiprocessing) when:** you have CPU-bound work — image processing, ML inference, heavy computation. `asyncio` does not speed up CPU work; it only hides I/O latency.

**Rule of thumb:** async scales concurrent connections cheaply; threads/processes scale CPU work.

**Interview answer:** "Async is a concurrency model, not a parallelism one. It's ideal when your requests spend most of their time waiting on I/O like database queries or external APIs. A single event loop handles hundreds of `await`-ing coroutines at once — no thread-switching overhead. For CPU-bound tasks, I'd offload to a process pool instead of blocking the loop."

---

### FastAPI vs Flask vs Django

**Choose FastAPI when:** you're building a JSON API and want async-first, automatic OpenAPI docs, and Pydantic validation with minimal boilerplate.

**Choose Flask when:** you need maximum flexibility or a very small app; synchronous-first, rich ecosystem, simpler mental model.

**Choose Django when:** you need a full-stack web app with ORM, admin, auth, and forms out of the box — batteries-included monolith.

**Trade-off FastAPI:** smaller ecosystem than Django; no built-in admin or ORM; you assemble your own stack.

#### Decision tree

```text
Need rapid JSON API development?          → FastAPI
Need async throughout?                    → FastAPI
Need admin panel + ORM built-in?          → Django
Need simple, synchronous, minimal?       → Flask
```

**Interview answer:** "FastAPI gives native async support, automatic OpenAPI/Swagger generation, and tight Pydantic v2 integration — all with minimal boilerplate. The trade-off is that you wire up more things yourself compared to Django. For a data pipeline API that's first and foremost I/O-heavy JSON endpoints, FastAPI's async model and auto-docs are a clear win."

---

### Pydantic v2 vs Alternatives

**Choose Pydantic v2 over marshmallow/attrs when:** you want Rust-backed validation speed, native JSON schema generation, and first-class FastAPI integration. Pydantic v2 is ~5-50x faster than v1 and marshmallow for model validation.

**Trade-off:** migration from v1 has breaking changes. Some third-party libraries lag behind v2 compat.

**Interview answer:** "Pydantic v2 blurs the line between schema definition and validation. The Rust core gives order-of-magnitude speedups for high-throughput APIs. For FastAPI specifically, it handles request parsing, response serialization, settings management, and error formatting all in one library — reducing the integration surface."

---

## Database Decisions

### PostgreSQL vs MySQL vs MongoDB (for primary store)

**Choose PostgreSQL when:** you need ACID transactions, complex queries (CTEs, window functions, JSONB), full-text search, or PostGIS. Best default for relational data.

**Choose MySQL when:** you're constrained by an existing stack, need master-replica replication out of the box at smaller scale, or need strict UTF8mb4 collation control.

**Choose MongoDB when:** your data is genuinely semi-structured with high shape variance, you need native horizontal sharding from day one, or your team is document-model-first.

**Common mistake:** choosing MongoDB to "avoid schema design." You still need schema design — you just lose the database's ability to enforce it.

#### Decision tree

```text
Need ACID + joins + complex aggregations?   → PostgreSQL
Need JSONB + relational hybrid?             → PostgreSQL (JSONB column)
Schema varies significantly per document?   → MongoDB
Truly need horizontal write sharding?       → MongoDB or Cassandra
"I don't want to write SQL"?                → still PostgreSQL + ORM
```

**Interview answer:** "PostgreSQL is my default for relational data. It has best-in-class MVCC, JSONB for semi-structured data, and window functions / CTEs that MongoDB's aggregation pipeline can't match. I'd reach for MongoDB only if the data truly has wide shape variance — like scraped web content where each source has a different structure — which is exactly the use case in this project's scraper layer."

---

### SQLAlchemy 2.0 ORM vs Raw SQL vs Query Builder

**Choose ORM when:** you want type-safe model definitions, auto-migration diffs (Alembic), and Python-level composition of queries. Trade-off: N+1 risk, slower for bulk operations.

**Choose raw SQL when:** you're writing complex analytics queries (window functions, CTEs) where the ORM abstraction adds noise. Use `text()` in SQLAlchemy for inline SQL.

**Choose query builder (Core / SQLAlchemy Core)** when: you want composable SQL without full ORM overhead.

**Rule:** Use ORM for CRUD, raw SQL for analytics, Core for bulk inserts.

**Interview answer:** "SQLAlchemy 2.0's `Mapped[T]` style gives you mypy-verifiable column definitions and async-native session management. I use the ORM for standard CRUD and let Alembic autogenerate migrations. For complex queries — window functions, CTEs, materialized view refreshes — I drop to `text()` or Core because the SQL is more readable than the equivalent ORM expression."

---

### Alembic vs `Base.metadata.create_all()`

**Alembic:** tracks schema version, supports incremental migrations, works in team environments, supports rollback.

**`create_all()`:** creates tables if they don't exist, idempotent, no version tracking, destroys data on schema changes (drop + recreate).

**Choose Alembic when:** you have any real data that must survive schema changes or you work in a team.

**Choose `create_all()`** when: testing (throwaway in-memory DB) or very early prototyping.

**In this project:** tests use `create_all()` with aiosqlite (throwaway). Production uses Alembic. Never mix both for the same DB.

**Interview answer:** "Alembic is essential for production. `create_all()` doesn't know what changed — it can't rename a column or add an index without recreating the table. Alembic generates diff-based migration scripts, stores a version hash in `alembic_version`, and lets you roll back. For tests I use `create_all()` against an in-memory SQLite DB because those tables are thrown away after each test run."

---

### Cache Cache: Yes or No?

**Add Cache when:** you have a hot read path that hits the same DB rows repeatedly (single-record lookups, session data, computed aggregates that are expensive to recompute). Expected hit rate > 50%.

**Skip Cache when:** your queries are already fast (< 5ms), data freshness requirements are strict, or you're adding complexity before measuring a bottleneck.

#### Choose TTL vs active invalidation

```text
Writes rare, staleness acceptable (1h)?       → TTL expiry only
Write happens, must immediately reflect?      → Active invalidation on write
High write volume, counting/analytics?        → Write-back (cache then async flush)
```

**Fail-open pattern:** if Cache is down, fall through to DB — never let cache failure return an error to the user. This is the pattern in `app/cache.py`.

**Interview answer:** "I treat Cache as a read accelerator, not a source of truth. The key decision is whether to use TTL or active invalidation. For single-record reads with infrequent writes, I use a 1-hour TTL with explicit invalidation on PATCH/DELETE. The cache is fail-open — if Cache is unavailable, requests fall back to the database transparently. I measure cache hit ratio via Prometheus counters before declaring the cache a win."

---

### Connection Pool Sizing

**Formula:** `pool_size ≈ PostgreSQL max_connections / num_app_instances`, with `max_overflow` covering burst.

**Typical default:** `pool_size=5`, `max_overflow=10`, `pool_pre_ping=True` per process.

**Problem sign:** "too many connections" error. Means total pool across instances exceeds `max_connections` (default 100).

**Interview answer:** "PostgreSQL has a hard connection limit (typically 100). Each Uvicorn worker process opens its own pool. So with 4 workers and `pool_size=5`, that's 20 connections per instance. At 3 instances you'd use 60 of 100 slots — still headroom. The async driver (asyncpg) is much more efficient than sync drivers because a single connection can pipeline multiple queries, so pool sizes can be smaller than you'd think."

---

## Distributed Systems Decisions

### Message Broker: Redpanda vs Kafka vs RabbitMQ vs Cache Streams

**Choose Redpanda when:** you want Kafka API compatibility without Zookeeper, simpler Docker setup, and better performance for single-node dev/learning.

**Choose Kafka when:** you're in an organization that already runs Kafka, need mature tooling (Confluent Schema Registry, KSQL), or need proven multi-datacenter replication.

**Choose RabbitMQ when:** you need complex routing (exchanges, topic/fanout patterns), traditional AMQP clients, or you primarily care about task queues over event logs.

**Choose Cache Streams when:** you already have Cache and your event volume is modest. Lower operational overhead; less durable than Kafka.

**Key distinction:** Kafka/Redpanda = durable event log (consumers can replay from any offset). RabbitMQ = message queue (messages disappear after consumption).

#### Decision tree

```text
Need replay / audit log?                  → Event Broker / Redpanda
Complex routing (fanout, topic)?          → RabbitMQ
Already have Cache, low volume?           → Cache Streams
Local dev simplicity + Kafka compat?     → Redpanda
```

**Interview answer:** "I chose Redpanda because it's Kafka API-compatible — same `aiokafka` producer/consumer code works unchanged — but runs as a single binary without Zookeeper. That cuts local setup from 3 containers to 1. For production on AWS, I'd switch to MSK Serverless which is also Kafka-compatible, so the application code never changes. The key architectural reason for Kafka over RabbitMQ here is the event log — consumers can replay events from any offset, which is essential for the CQRS read model in analytics."

---

### Vector Store: Qdrant vs pgvector vs Chroma vs Pinecone

**Choose Qdrant when:** you want a self-hosted, purpose-built vector DB with a rich filtering API, gRPC interface, and support for high-dimensional HNSW indexing. Good for learning the dedicated vector DB model.

**Choose pgvector when:** you're already on PostgreSQL, data volume is moderate (< 10M vectors), and you want to avoid an extra service. Trade-off: not as fast as dedicated vector DBs at scale.

**Choose Chroma when:** you want dead-simple local embedding storage for prototyping. Not production-grade at scale.

**Choose Pinecone when:** you're going fully managed, don't want to operate infrastructure, and can accept vendor lock-in.

#### Decision tree

```text
Already on Postgres, < 10M vectors?       → pgvector (simpler)
Need scale + filtering + self-hostable?   → Qdrant
Prototyping / local only?                 → Chroma
Fully managed, cloud-first?               → Pinecone
```

**In this project:** Qdrant is primary (Phase 3, teaches dedicated vector DB operations); pgvector is added in Phase 5 for direct comparison.

**Interview answer:** "For a self-hosted learning platform, Qdrant is the right call because it teaches the vector database model directly — collections, HNSW indexing, payload filtering. pgvector is great when you want to stay in PostgreSQL and avoid operational complexity, but at tens of millions of vectors with complex metadata filters, dedicated vector DBs outperform it significantly. In this project I run both — Qdrant for the primary pipeline, pgvector in Phase 5 to make the trade-offs tangible."

---

### HTMX vs React / Vue / Next.js

**Choose HTMX when:** your UI is server-rendered, interactions are mostly "fetch partial HTML and swap it in", you're a backend developer who wants to avoid a JS build pipeline, and your team owns Python/Jinja templates.

**Choose React/Next.js when:** you need rich interactive state (drag-drop, realtime collaborative editing, complex client-side filtering), or you have a dedicated frontend team.

**Trade-off HTMX:** limited client-side state management; SSE/WebSocket is possible but not as smooth as React's ecosystem.

**Interview answer:** "HTMX lets backend developers build interactive UIs without a JavaScript framework. Each user interaction is an HTTP request that returns an HTML fragment — the server stays the source of truth. For a data explorer dashboard with pagination, search, and SSE metrics, HTMX + Jinja2 covers the requirements without a build system. React would be the right call if the UI needed complex client-side state — say, a realtime collaborative editor — but for this dashboard it'd be premature."

**Phase 6 shape:** `services/dashboard/` serves the three browser views (`/`, `/search`, `/metrics`); HTMX handles partial swaps and infinite scroll, while SSE streams live metrics from Prometheus.

---

### Cloud Compute: ECS Fargate vs EKS vs Lambda

**Choose ECS Fargate when:** you want managed containers without operating a Kubernetes control plane. Good balance of flexibility and operational simplicity. Right for most "run this service 24/7" workloads.

**Choose EKS when:** you need Kubernetes-native tooling (Helm charts, CRDs, service mesh), your team already knows Kubernetes, or you need features like pod auto-scaling based on custom metrics.

**Choose Lambda when:** your workload is event-triggered, bursty, and can tolerate cold starts. Cost-optimized for intermittent workloads.

#### Decision tree

```text
Event-driven, bursty, short-lived?        → Lambda
Long-running service, team knows K8s?     → EKS
Long-running service, want managed?       → ECS Fargate
```

**In this project:** ECS Fargate. Kubernetes is a separate learning project — it's too large a scope increase to learn alongside distributed systems patterns.

**Interview answer:** "ECS Fargate removes the Kubernetes control plane operational burden while still giving you container portability. You define task definitions, assign them to a cluster, and AWS handles the underlying EC2 instances. The cost is slightly less flexibility than EKS — no Helm, no custom scheduling — but for a straightforward multi-service deployment that's not a constraint. I'd move to EKS when the team has Kubernetes expertise and needs advanced scheduling or a service mesh."

---

### MongoDB vs PostgreSQL JSONB (for scraped data)

**Choose MongoDB when:** documents truly have different shapes per source (scraping 10 different sites, each returning a different JSON structure), you need native horizontal sharding, or you need MongoDB-specific operators like `$lookup` with unwind.

**Choose PostgreSQL JSONB when:** you can tolerate slight query verbosity for `->>`/`@>` operators, your JSON is semi-structured but bounded, and you want to keep one database.

**In this project:** MongoDB for scraped raw documents (genuinely varied shape per scraping source), PostgreSQL for the normalized `records` table.

**Interview answer:** "I use MongoDB for the scraper layer because the raw document shape from each source is genuinely different — a Hacker News item looks nothing like a JSONPlaceholder post or a Playwright-scraped article. Storing all of them in a PostgreSQL JSONB column works, but MongoDB's document model is a more natural fit and teaches the document database paradigm directly. The processed, normalized data still lands in PostgreSQL where I can run window functions and CTEs on it."

---

## Observability Decisions

### Structured Logging vs `print()`

**Always structured logging in services.** JSON logs are machine-parseable — you can grep, aggregate, and alert on them in log aggregators (Loki, Splunk, Datadog). Plain text is fine for scripts.

**Key fields every log entry must have:** `timestamp`, `level`, `event` (what happened), `cid` (correlation ID to trace a request end-to-end), and relevant context (record ID, source, etc.).

**Interview answer:** "Structured JSON logging is non-negotiable for a service that runs 24/7. In production you can't SSH in and read logs — you need a log aggregator. JSON lets you write queries like 'show me all records from source X that failed in the last hour' without parsing regexes. The correlation ID is the key: inject it at the request boundary (middleware), propagate it through all function calls, and you can reconstruct the full lifecycle of any request."

---

### Metrics: What to Instrument

#### The Four Golden Signals (SRE)

- **Latency** — how long requests take (histogram, P50/P95/P99)
- **Traffic** — requests per second (counter)
- **Errors** — rate of failed requests (counter, labeled by status code)
- **Saturation** — how full the resource is (DB connection pool usage, CPU)

**Rule:** instrument at service boundaries (HTTP handler entry/exit + DB query timing). Don't instrument every internal function — noise hides signal.

**Interview answer:** "I instrument the four golden signals at every service boundary. For this FastAPI app that means `prometheus-fastapi-instrumentator` for HTTP latency/traffic/errors, a custom counter for cache hits/misses, and connection pool saturation. The alert thresholds I target are P95 latency < 500ms and error rate < 1%. Anything beyond that I investigate before setting an alert — arbitrary thresholds create alert fatigue."

---

### Distributed Tracing: When to Add

**Add tracing when** you have more than one service and need to correlate work across service boundaries (e.g., ingestor HTTP span → processor Kafka consumer span → inference embed span). Logs + metrics alone can't show you where time was spent across services.

**OpenTelemetry vs proprietary SDKs:** Always OpenTelemetry. Vendor-neutral, swap the exporter (Jaeger, Tempo, Datadog) without changing application code.

**Interview answer:** "Tracing answers the question logs can't: 'which service is slow and why?' In a multi-service setup, a slow request might involve the ingestor, a Kafka consumer, and a vector DB call. A trace stitches those spans together with a shared `trace_id`. I inject the trace ID into structured log output so I can jump from a Grafana trace view directly to the correlated log lines."

---

## Security Decisions

### JWT vs Session-Based Auth

**Choose JWT when:** stateless architecture (no server-side session store), cross-service auth (pass the token between services), or mobile/SPA clients.

**Choose sessions when:** you need immediate revocation (log attacker out now, not after token expiry), you're building a traditional server-rendered web app, and you have a session store (Cache).

**JWT trade-off:** you can't invalidate a token before expiry without a denylist (which re-introduces state). Keep token TTL short (15–60 min) and use refresh tokens.

**Interview answer:** "JWT works well for this API because the services are stateless — each microservice can verify a token locally without a shared session store. The trade-off is that compromised tokens remain valid until expiry. I mitigate this by keeping access token TTL at 15 minutes and requiring refresh tokens for long-lived sessions. For a banking app or high-security context I'd layer in a Cache denylist for immediate revocation."

---

### Input Validation: Where to Validate

**Validate at every trust boundary** — the API boundary (Pydantic schemas), the database boundary (constraints + parameterized queries), and service-to-service calls (same Pydantic schemas).

**Never** sanitize and then trust: validate the schema, reject what doesn't match, never pass raw user input to SQL string interpolation or shell commands.

**Interview answer:** "I validate as early as possible — at the HTTP layer with Pydantic, which rejects malformed requests before they touch business logic. The database adds a second layer via CHECK constraints and parameterized queries (which prevent SQL injection categorically). The key principle is fail early and fail loudly: a 422 Validation Error at the API boundary is better than a cryptic DB error or, worse, a silent data corruption."

---

## Resilience Decisions

### Circuit Breaker: When to Use

**Add a circuit breaker when** you're calling a downstream service that could fail or degrade slowly. Without it, slow downstream failures create a cascade: your service's thread pool fills with slow requests, your service becomes slow, its callers back up, and so on.

#### Three states

- **CLOSED** — calls go through normally
- **OPEN** — calls are short-circuited immediately (fast fail)
- **HALF_OPEN** — one probe request goes through to test recovery

**Apply to:** outbound HTTP calls to external APIs, Kafka producer publish, MongoDB/Qdrant writes (anything that could slow or fail).

**Interview answer:** "The circuit breaker prevents a slow/failing downstream from exhausting your connection pool or blocking your event loop. When the failure threshold trips, subsequent calls fail immediately — the caller gets a fast error instead of waiting on a 30-second timeout. This is especially important in async Python where a flood of slow awaits can starve the event loop. I configure the threshold empirically: typically 5 failures in a 10-second window before the circuit opens."

---

### Saga Pattern: Distributed Transactions

**Use the Saga pattern when** a business operation spans multiple services (each with their own DB) and you can't use a two-phase commit (too slow, too coupled).

**Choreography-based Saga:** each service publishes an event on success, the next service is triggered by that event. No central coordinator. Simpler but harder to track failures.

**Orchestration-based Saga:** a central orchestrator calls each service step and handles compensations explicitly. More visible, easier to debug, but adds a coordination chokepoint.

**Interview answer:** "Two-phase commit across microservices is impractical at scale — it creates tight coupling and blocking locks across service boundaries. Sagas replace atomic transactions with a sequence of local transactions, each publishing an event to trigger the next step. If step N fails, compensation transactions undo steps 1 through N-1. In this project the scrape→embed→store pipeline uses a choreography-based saga: each stage publishes an event, the next service consumes it. A DLQ on the Kafka topic catches failures for later replay or manual review."

---

## DSA in Production

### When to Use Each Data Structure

**Bloom Filter:** check if a URL/ID has been seen before without storing all seen IDs. False positives possible, false negatives never. Use for scraper URL deduplication where the cost of a false positive (re-scraping) is low and the cost of storing all URLs in Cache is high.

**LRU Cache:** any hot data with a bounded working set (embedding cache, user profile cache). Python's `functools.lru_cache` for pure functions, `cachetools.LRUCache` for mutable data.

**Min-Heap / `heapq`:** top-N or bottom-N selection in O(N log K) instead of O(N log N) sort. Use when you need the top 10 records out of 1M without sorting all 1M.

**Sliding Window:** rate limiting (count requests in last N seconds), moving averages over time-series data. Already in `app/rate_limiting_advanced.py`.

**Consistent Hashing:** distribute load across N nodes such that adding/removing a node rebalances only K/N keys instead of all. Used for Kafka partition key selection to ensure related events go to the same partition (and thus same consumer).

**Interview answer template:** "I reach for X when Y is the bottleneck. For example, a Bloom Filter when I need sub-millisecond URL deduplication at scraping scale — storing every seen URL in Cache would use gigabytes of memory. A Min-Heap when I need top-10 out of a million rows — heapq.nlargest() is O(N log 10) vs O(N log N) for a full sort."

---

## Phase 7: Cloud Deployment — Infrastructure Decisions

### ECS Fargate vs EKS (Kubernetes)

#### Choose ECS Fargate when

- 1–10 microservices (not a platform team running 100+ services)
- Learning distributed patterns (not learning Kubernetes operations)
- Budget matters (ops labor is expensive; managed is cheaper)
- CI/CD is simple (`aws ecs update-service` vs `kubectl set image` + GitOps)

#### Choose EKS when

- 20+ microservices (Kubernetes pays for itself in automation)
- You have a platform team to own upgrades, CRDs, CNI
- You need service mesh (Istio) or advanced networking
- You're already all-in on Kubernetes elsewhere

**Trade-off Fargate:** less power/flexibility than Kubernetes; can't customize CNI, no node access.

**Cost comparison** (monthly, dev + prod):

| Option | Dev | Prod | Total | Labor |\n| ------ | --- | ---- | ----- | ------ |
| Fargate | $85 | $280 | $365 | ~2 hrs/month (none post-setup) |
| EKS | $100+ | $400+ | $500+ | ~20 hrs/month (node mgmt, upgrades) |

**Interview answer:** "For a learning project building distributed systems patterns, ECS Fargate is the right choice. It eliminates the distraction of node management and lets me focus on service-to-service communication, resilience patterns, and CI/CD. If this project grew to 50+ microservices and I needed to self-heal nodes or run a service mesh, EKS would make sense. But Kubernetes is a separate learning project; Fargate is the pragmatic default."

---

### RDS PostgreSQL vs Aurora vs DocumentDB (AWS managed databases)

#### Choose RDS PostgreSQL when

- You know SQL well (strong ACID, complex queries, CTEs, window functions)
- Existing PostgreSQL expertise in team
- Cost matters (RDS is cheapest AWS SQL option)
- Schema is stable

#### Choose Aurora PostgreSQL when

- You need read replicas + automatic failover (but costs 2-3x more)
- You exceed 200 concurrent connections (Aurora has higher limit)
- You need fast backups/restore
- You're willing to pay for Serverless

#### Choose DocumentDB when

- Data is genuinely document-shaped (high schema variance)
- You prefer document queries over SQL
- You don't need complex aggregations (CTEs, window functions)

**Trade-off RDS:** manual read replica setup, smaller connection pool (100 default vs 3000 Aurora), no built-in serverless option.

**Interview answer:** "I chose RDS PostgreSQL for primary storage because the data is relational, I need ACID guarantees, and window functions for analytics (Phase 5). MongoDB is also in the stack but specifically for scraped documents (Phase 2) where schema variance is expected. Aurora would cost 3x more; we hit RDS limits only if we exceed 1000 concurrent connections, which won't happen with ECS running 2 tasks."

---

### ElastiCache Cache vs Memcached vs DynamoDB (managed caches)

#### Choose ElastiCache Cache when

- You need persistence (AOF, snapshots) or complex data structures (sorted sets, streams)
- You want Lua scripting for atomic operations
- You prefer multi-AZ failover (ElastiCache cluster mode)

#### Choose Memcached when

- You only need simple key-value cache (no structures)
- You want simplicity and speed (simpler than Cache)
- You don't need persistence

#### Choose DynamoDB when

- Cache is really a database (queries are complex)
- You want full AWS-managed (no patching)
- You don't mind eventual consistency

**Interview answer:** "ElastiCache Cache with TLS + AUTH is the middle ground for this project. It gives me persistence (important for development state), expiration policies (TTL), and failover in production (Multi-AZ). Memcached would be faster but offers no persistence; DynamoDB would require you to treat it as a database, which adds complexity."

---

### MSK Serverless (AWS-managed Kafka) vs Self-Managed Kafka vs Redpanda

#### Local (docker-compose, Phase 1–6)

- Use Redpanda: no Zookeeper, simpler Docker setup, Kafka-compatible API

#### Production (Phase 7 onwards)

- Use MSK Serverless: AWS-managed, IAM auth (no password management), auto-scaling, high availability

| Option | Setup Time | Ops Labor | Cost (dev) | Cost (prod) |
|--------|------------|-----------|-----------|------------|
| Redpanda (local) | 2 min | 0 hrs | $0 | N/A (not prod) |
| MSK Serverless | 5 min (Terraform) | ~1 hr/month | ~$0.30 per million requests | $500+/month |
| Self-managed Kafka | 30 min | 10+ hrs/month | varies | varies |

**Interview answer:** "For local development, Redpanda is unbeatable — just pull a Docker image, no Zookeeper. For AWS production, MSK Serverless eliminates all broker management: AWS handles failovers, upgrades, and scaling. IAM authentication integrates with our GitHub OIDC role; we never store passwords. The tradeoff is cost (~500/mo for prod brokers), but that's paid labor you'd otherwise spend on broker patches and disk management."

---

### S3 Backend + Native Lockfile State Locking (Terraform)

#### Choose S3 + lockfile when

- Team > 1 person (multiple people apply Terraform)
- You need audit trail (S3 versioning, lockfiles prevent concurrent writes)
- You want remote state (not .tfstate on laptop)

#### Choose local state only when

- Solo project, never collaborating
- You're OK with merge conflicts if two people apply simultaneously

**Trade-off remote state:** adds some setup complexity (S3 bucket policy, versioning, encryption), but pays for itself immediately with team > 1.

**Interview answer:** "Even for a solo project, I put Terraform state in S3 with lockfile locking. It forces good practices (versioning, audit trail) and if I add a collaborator later, we don't have to redo the setup. The setup is still lightweight and removes local-state risk."

---

### GitHub OIDC vs Long-Lived Access Keys (CI/CD authentication)

#### Choose GitHub OIDC when

- You're deploying from GitHub Actions
- You want no long-lived secrets in GitHub Secrets
- You want CloudTrail audit trail of all role assumptions

#### Choose long-lived keys only when

- You have no alternative (old CI/CD system)
- You're OK with rotating keys every 90 days
- You're OK with "Who made this deploy?" being hard to trace

**Trade-off OIDC:** setup is a bit more complex (IAM provider + role + trust policy), but it's one-time per AWS account.

**Interview answer:** "I use GitHub OIDC instead of AWS Access Keys in GitHub Secrets. GitHub generates a JWT per workflow run; we exchange it for temporary AWS credentials scoped to just what the CI/CD needs (ECR push). If that credential is ever exposed, it's only valid for a few minutes and only for ECR. With long-lived keys, a compromise means rotating all your credentials. This is a best practice and barely more effort than the naive approach."

---

### dev vs prod environment strategy (different instance types, Spot pricing)

#### Separation Strategy

- **dev:** Fargate Spot (saves 70%), db.t3.micro, 1 NAT Gateway, 14-day backup retention
- **prod:** Fargate On-Demand, db.t3.medium Multi-AZ, 3 NAT Gateways (HA), 90-day backups

#### Why separate

- Costs are different (dev should be cheap to experiment)
- HA requirements differ (dev can tolerate outages; prod cannot)
- Testing data doesn't need 90-day retention (noise in backups)

**Cost impact:** ~$85/month dev, ~$280/month prod. Shared environment would cost ~$280/month always-on, so we save money by being cheap in dev.

**Interview answer:** "Environments should optimize for their use case, not copy production. Development is cheap (Spot instances, micro DB, minimal backups) and okay with outages. Production is bulletproof (on-demand, Multi-AZ, long backups) but costs more. The 70% Spot savings in dev makes it easier to experiment with expensive services like Qdrant and MSK Serverless without guilt."

---

## Deployment & Container Decisions

### Docker Build Optimization: BuildKit vs Legacy Builder

**Choose BuildKit when:** you're doing multi-stage builds with repeated package installations (apt, pip). BuildKit's `--mount=type=cache` persists layer cache across builds, yielding 3-5x rebuild speedup.

**Choose Legacy Builder when:** you have very simple single-stage Dockerfiles or need exact reproducibility without any caching.

**In practice:** always use BuildKit for production. The syntax is cleaner, cache mounts reduce bandwidth, and it's been stable since Docker 20.10.

#### Setup

```bash
export DOCKER_BUILDKIT=1  # Permanent in ~/.bashrc
docker build -t service:latest .  # BuildKit enabled
```

#### Key patterns

- `# syntax=docker/dockerfile:1.4` as first line enables BuildKit features
- `SHELL ["/bin/bash", "-o", "pipefail", "-c"]` after each FROM (fail-fast)
- `apt-get clean` instead of `rm -rf /var/lib/apt/*` (respects layer caching)

**Interview answer:** "BuildKit's cache mounts are a game-changer for multi-stage builds. Instead of re-downloading 200MB of apt packages on every build, the cache persists. Second build goes from 3 minutes to 30 seconds. For a team doing frequent local builds and CI/CD pushes, the 3-5x speedup justifies the small setup effort."

---

### Base Image Pinning: Digest vs Latest vs Version Tag

**Choose digest pinning when:** you need reproducible builds and want to prevent surprise breakage from base image updates. Trade-off: requires manual updates when patching.

**Choose version tags (`:3.14-slim`) when:** you're okay with minor patches applied automatically, but want predictable major versions.

**Choose `latest` when:** this is a learning project and manual updates aren't a concern.

**Security rationale:** uncontrolled base image drift can introduce vulnerabilities without your knowledge. Pinning gives you explicit control and audit trail.

#### Example

```dockerfile
# PINNED — reproducible, secure
FROM python:3.14-slim@sha256:bc389f7dfcb21413e72a28f491985326994795e34d2b86c8ae2f417b4e7818aa

# NOT PINNED — auto-patches, less control
FROM python:3.14-slim
```

**Interview answer:** "I pin base image digests in production Dockerfiles for reproducibility. Every build produces identical layers across environments, which is critical for security scanning — we know exactly what's in the image. The trade-off is that upgrading the base image requires a deliberate digest change, which forces a code review. That's actually a feature: you know when the base image changed."

---

### Container Vulnerability Scanning: Trivy vs Snyk vs Clair

**Choose Trivy when:** you want fast, free, open-source scanning for OS-level and application vulnerabilities. No subscriptions, can run offline after initial DB pull.

**Choose Snyk when:** you're an org that needs managed scanning across multiple repos, developer workflows integration, and commercial support. Requires paid plan for advanced features.

**Choose Clair when:** you're running a private Docker registry and want scanning integrated at the infrastructure level (registry hooks).

**In this project:** Trivy is ideal for GitHub Actions workflows and local development because it's zero-cost and requires no external accounts.

#### What each scans

- **Trivy**: OS packages (libc, openssl, curl), Python packages, Node packages, image misconfigurations
- **Snyk**: Same + supply chain analysis + policy enforcement + license compliance
- **Clair**: OS + application packages, designed for registry integration

**Interview answer:** "Trivy covers all our scanning needs: it finds OS CVEs (OpenSSL, curl) and Python CVEs via pip-audit. The SARIF output integrates with GitHub Code Scanning for visibility. For a learning project, Trivy's free tier is perfect. Snyk adds compliance and managed workflows — worth considering if the org needs SOC2 or if multiple teams are shipping containers."

---

### Dependency Scanning: pip-audit vs Safety vs Bandit

#### pip-audit (Python dependencies)

- Checks for known CVEs in pip packages
- Official PyPA tool, trusted source
- Can auto-upgrade vulnerable packages
- Pre-commit hook friendly

#### Safety (Python dependencies)

- Older tool, less frequently updated
- Requires online DB check (slower)
- Deprecated in favor of pip-audit for most use cases

#### Bandit (Python code security)

- Scans code for security anti-patterns (hardcoded secrets, SQL injection risks, etc.)
- Complementary to pip-audit (different scope: code vs dependencies)
- Often paired with pip-audit for comprehensive security

**Choose pip-audit + Bandit when:** running a Python project. Use pip-audit for dependency CVEs, Bandit for code issues.

**Skip Safety:** pip-audit is newer, faster, and official PyPA endorsement.

**Interview answer:** "pip-audit is my first stop for Python security — it checks if any pip packages have known CVEs. Bandit complements it by scanning for code-level issues like hardcoded credentials or unsafe SQL usage. Together they cover both supply chain (which packages are vulnerable) and code (are we using vulnerable patterns). Running both in pre-commit and CI/CD catches 95% of common issues before code reaches production."

---

## Quick Reference Decision Matrix

| Question                | Answer                                                                 |
| ----------------------- | ---------------------------------------------------------------------- |
| I/O-bound or CPU-bound? | I/O → async; CPU → processes                                           |
| API framework?          | FastAPI (async JSON) / Django (full-stack) / Flask (simple)            |
| Primary DB?             | PostgreSQL almost always; MongoDB for genuinely varied document shapes |
| ORM vs raw SQL?         | ORM for CRUD; raw SQL for analytics                                    |
| Cache or not?           | Only after measuring; fail-open pattern                                |
| Message broker?         | Redpanda (learning/dev); Kafka/MSK (prod)                              |
| Vector store?           | pgvector (existing Postgres, < 10M); Qdrant (scale + dedicated)        |
| Frontend?               | HTMX (backend devs, server-rendered); React (complex SPA)              |
| Cloud compute?          | ECS Fargate (managed, learning); EKS (K8s expertise required)          |
| Cloud database?         | RDS PostgreSQL (cost, simplicity); Aurora (HA + replicas, 3x cost)     |
| Cloud cache?            | ElastiCache Cache (persistent, structures); Memcached (simple, fast)   |
| Cloud message queue?    | MSK Serverless (managed, IAM auth); self-managed Kafka (control)       |
| Infrastructure code?    | Terraform (popular, HCL); CloudFormation (AWS-native, verbose)         |
| Terraform state?        | Remote S3 + lockfile locks (team-safe); local (solo, risky)             |
| CI/CD secrets?          | GitHub OIDC (no AWS keys, audit trail); AWS access keys (simple, risky) |
| Auth?                   | JWT (stateless, multi-service); Sessions (need immediate revocation)   |
| Distributed txn?        | Saga pattern (event choreography)                                      |
| Schema migrations?      | Alembic (production); `create_all()` (tests only)                      |
| Docker build system?    | BuildKit with cache mounts (fast rebuilds); Legacy builder (simple)    |
| Base image pinning?     | Digest pinning (reproducible, secure); version tags (auto-patch)      |
| Container scanning?     | Trivy (free, fast, GitHub integration); Snyk (managed, compliance)     |
| Dependency scanning?    | pip-audit (Python CVEs); Bandit (code security issues)                 |
| Security gates?         | Pre-commit hooks (local); GHA CI/CD (automated verification)           |
