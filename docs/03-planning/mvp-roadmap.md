# MVP & Post-MVP Roadmap

Track: C — Architecture and Platform Strategy

This document defines the two operating modes, the tech stack per phase, and the functionality-to-technology mapping with reasoning.

---

## Operating Modes

### MVP Mode

Use during active feature stabilization. Favors speed and predictable local feedback.

#### Runtime profile

- Start the local stack with Docker Compose.
- Keep schema setup simple with startup bootstrap behavior.
- Focus on source-registry, probe loop, scorecards, and drift slices.

#### Test gate

```bash
DATABASE_URL_TEST=sqlite+aiosqlite:///:memory: uv run pytest tests/ services/ingestor/tests/ -q -m "unit"
DATABASE_URL_TEST=sqlite+aiosqlite:///:memory: uv run pytest services/ingestor/tests/integration/test_source_registry_api.py -q
```

### Post-MVP (MVP+) Mode

Use after MVP is shipped and release hardening begins.

#### Runtime profile

- Keep the same app surface and services.
- Enable migration-first schema workflow.
- Require stronger release validation and operational checks.

#### Test gate

```bash
DATABASE_URL_TEST=sqlite+aiosqlite:///:memory: uv run pytest tests/ services/ingestor/tests/ -q -m "unit"
env -u DATABASE_URL_TEST uv run pytest tests/ services/ingestor/tests/ -q -m "integration or e2e"
```

### When to Switch

Switch from MVP to MVP+ when all are true:

1. Core vertical slices are stable under daily development.
2. API behavior is locked for release candidates.
3. You are ready to enforce migration-first database changes.

---

## Gap #1: Tech Stack per Phase

| Component | MVP (local Docker) | Post-MVP (AWS) | Rationale |
|-----------|-------------------|----------------|-----------|
| **API Framework** | FastAPI (Uvicorn) | FastAPI (Uvicorn) | Same codebase; async-first, auto-OpenAPI, Pydantic v2 |
| **Database** | PostgreSQL 17 (Docker) | RDS PostgreSQL 17 | Same SQL; opt-in observations RLS verifies tenant isolation locally; RDS adds managed backups, Multi-AZ, IAM auth |
| **Cache** | Cache 7 (Docker) | ElastiCache Cache 7.1 | Same Cache protocol; ElastiCache adds TLS, AUTH, Multi-AZ |
| **Message Broker** | Redpanda (Docker) | MSK Serverless | Kafka-compatible; `aiokafka` code unchanged; IAM auth |
| **Vector Store** | pgvector (dedicated `inference-db`) | pgvector (managed Postgres) | Real as of Phase 2 of the AI-augmented observatory plan; Qdrant deferred, see ADR-015 |
| **Object Store** | MinIO (optional) | AWS S3 | Same S3 API via minio-py client |
| **Frontend** | Streamlit (MVP) → HTMX+Jinja2 | HTMX+Jinja2 (dashboard service) | MVP uses Streamlit for quick UI; HTMX added for production dashboard |
| **Agent/LLM** | LangGraph + Anthropic | LangGraph + Anthropic | Real as of Phase 3; dual-model: claude-haiku-4-5 (classify), claude-sonnet-4-5 (deep analyze). `/analyze`'s RAG path separately still uses OpenAI (unverified, no key available) |
| **Auth** | JWT (PyJWT) | JWT (PyJWT) + OIDC optional | Stateless, multi-service; refresh tokens for long sessions |
| **Observability** | structlog + Prometheus + Tempo | Same + CloudWatch + Sentry | OTel tracing and Tempo are wired locally; add managed alternatives in cloud |
| **Container Runtime** | Docker Compose | ECS Fargate | Same Docker images; Fargate eliminates node management |
| **Infra as Code** | None (local only) | Terraform | S3 backend + lockfile locking; OIDC for CI/CD |
| **CI/CD** | GitHub Actions | GitHub Actions | Same workflows; OIDC instead of long-lived keys in prod |
| **Notifications** | None | Slack, Telegram, webhook, email | Deferred; multi-channel alerting via ingestor/notifications.py |

---

## Gap #2: Feature → Technology Mapping with Reasoning

| Feature | MVP? | Technology | Why not alternatives | ADR Ref |
|---------|------|-----------|---------------------|---------|
| **Source Registry CRUD** | ✅ | FastAPI + SQLAlchemy 2.0 | Flask lacks async/auto-docs; Django too heavy for single service | — |
| **Probe Scheduler** | ✅ | APScheduler + httpx | Celery too heavy for single-process probes; cron lacks API integration | — |
| **Scorecard Aggregation** | ✅ | SQL `PERCENTILE_CONT` | Avoids Python post-processing; single query vs. Python loop over rows | — |
| **Contract Drift Detection** | ✅ | SHA-256 fingerprint + field diff | Fingerprint short-circuits 99% of checks; no external service needed | — |
| **WebSocket Real-Time** | ✅ | Cache pub/sub | Kafka too heavy for fan-out to N clients; Cache pub/sub is fire-and-forget | — |
| **Streamlit Dashboard** | ✅ | Streamlit | Fastest path to visual UI for MVP; replaced by HTMX dashboard post-MVP | — |
| **JWT Auth + RBAC** | ✅ | PyJWT + FastAPI Depends | Stateless, no session store; refresh tokens mitigate JWT revocation gap | — |
| **Rate Limiting** | ✅ | Redis-backed token bucket | Production v1 is keyed by tenant and subject; Cache-disabled local runs use an in-process fallback. Fixed-window examples are opt-in learning-lab routes. | — |
| **Circuit Breaker** | ✅ | Custom asyncio impl | No lib match for async + custom state machine; 100 LOC vs heavy dependency | ADR-004 |
| **Structured Logging** | ✅ | structlog + JSON | Machine-parseable, correlation IDs via ContextVar | — |
| **Prometheus Metrics** | ✅ | prometheus-client | Standard; prometheus-fastapi-instrumentator for HTTP metrics | — |
| **OpenTelemetry Tracing** | ✅ | OTLP + Tempo | Ingestor is instrumented, exports OTLP spans to the local Tempo collector, and correlates traces with Loki logs | — |
| **Kafka Event Streaming** | ✅ | Redpanda (aiokafka) | Redpanda = Kafka API, no Zookeeper; MSK Serverless in prod | ADR-001 |
| **Kafka DLQ** | ✅ | Custom aiokafka routing | Poison pill isolation; retry 3x then forward to DLQ topic | ADR-004 |
| **Agent Enrichment** | ✅ | LangGraph StateGraph | Real as of Phase 3. Dual-model: claude-haiku-4-5 (classify_severity), claude-sonnet-4-5 (draft_analysis) — always deep for draft, since Phase 1's trigger gate already pre-filters to critical/breaking only | ADR-012 |
| **Agent HITL Review** | ✅ | LangGraph checkpointer + Postgres | Real as of Phase 3 (not Cache, as originally speculated — `langgraph-checkpoint-postgres` on the ingestor's own `db`). Pause at human_review; resume via `POST /api/v1/agent/runs/{run_id}/resume`, verified live including a resume call in a separate process | ADR-012 |
| **Scraping (HTTP/HTML/Browser)** | ❌ | httpx + BeautifulSoup + Playwright | Factory pattern for 3 scraper types; Semaphore(5) for concurrency | — |
| **MongoDB Document Store** | ❌ | Motor (async MongoDB) | Genuinely varied document shapes per source | — |
| **Vector Search** | ✅ | pgvector (dedicated instance per service) | Real per-service DB ownership without a second engine to operate; Qdrant deferred, not rejected — see ADR-015 | ADR-015 |
| **MCP Server** | ✅ | FastMCP (stdio) | Standalone `fastmcp` package chosen over the bundled `mcp.server.fastmcp.FastMCP` for multi-transport support (stdio now, `streamable-http` later with no rework); hand-written `@mcp.tool()` wrappers over the real ingestor HTTP API (own `mcp-service` JWT login), not in-process repository imports or OpenAPI auto-generation | — |
| **HTMX Dashboard** | ❌ | HTMX + Jinja2 + SSE | No JS build pipeline; server-side rendering keeps source of truth in backend | ADR-003 |
| **Notifications** | ❌ | Multi-channel (Slack, Telegram, webhook, email) | httpx-based; fail-open design | — |
| **AWS Deployment** | ❌ | Terraform + ECS Fargate + RDS + ElastiCache + MSK | Fargate eliminates K8s ops; Terraform for IaC; OIDC for CI/CD auth | ADR-008 |
| **Production Monitoring** | ❌ | Grafana + Alertmanager + GlitchTip | Prometheus data → Grafana dashboards; SLO-based alerting | — |

---

## Audit Gaps

See [audit-gaps.md](audit-gaps.md) for known gaps between the planned MVP/post-MVP scope and actual implementation status.

## Post-MVP Execution

See [`docs/.plans/post-mvp-nfr-roadmap.md`](../.plans/post-mvp-nfr-roadmap.md) for the phased, NFR-first execution plan (tracing, resilience, retention, auth, RLS, quality gates, AI-native depth, cloud handoff) that this roadmap's "Post-MVP (MVP+) Mode" hands off to.

## Changelog

- 2026-07-24: Phase 6C adds a weekly/manual, isolated k6 smoke workflow. It exercises
  registration, JWT login, health, and a protected source read against ephemeral Postgres,
  while retaining JSON summaries as baselines before a latency SLO is made blocking.
- 2026-07-24: Phase 6B quality ratchet adds separate ingestor and inference coverage artifacts
  to CI. The dedicated inference integration job runs against pgvector Postgres with deterministic
  embeddings and enforces an 85% production-source baseline; the existing ingestor integration
  threshold remains 40%.
- 2026-07-23: Phase 3A retention implemented as a disabled-by-default, manually invoked
  archive lifecycle. Observations older than 30 days by event timestamp are copied and verified
  in `observations_archive` before their bounded hot-table batch is deleted. Native partitioning,
  object storage, and retention for other records remain deferred to later phases.
