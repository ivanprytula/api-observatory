# Technology Decisions & ADR Index

Track: C — Architecture and Platform Strategy

This document indexes every architecture decision record (ADR) and key technology choice in the platform. Use it as a decision rationale map: find the question, read the summary, click through to the full ADR for context/alternatives/consequences.

---

## How to Use

Each entry follows: **Question → Decision → Rationale (1-2 lines) → ADR link**.

For in-depth trade-off analysis ("why not X?"), open the linked ADR file.

---

## ADR Index

### 001: Kafka vs RabbitMQ — Message Broker

**Decision**: Redpanda (Kafka-compatible, no Zookeeper) for local development. A managed Kafka
service is deferred until a real asynchronous production workload justifies it.

**Rationale**: Redpanda gives Kafka wire-protocol compatibility with a single binary. The event-log
model supports replay and partition/consumer-group exercises without claiming that Stage 0 needs a
managed broker.

[→ ADR 001](adr/001-kafka-vs-rabbitmq.md)

---

### 015: `inference`'s Dedicated pgvector Postgres — Vector Database

**Decision**: pgvector on a Postgres instance dedicated to `inference` (not shared with the ingestor). No Qdrant today — deferred pending a concrete need, not rejected.

**Rationale**: Real per-service database ownership without taking on a second database *engine* to operate. Supersedes ADR 002, which was written for an earlier, larger design that predates the current MVP scope and was never archived when the project pivoted.

[→ ADR 015](adr/015-inference-dedicated-pgvector-postgres.md) (ADR 002, superseded: [stub](adr/002-qdrant-vs-pgvector.md))

---

### 003: HTMX vs React — Frontend Framework

**Decision**: Keep the implemented Streamlit dashboard for the current playground. HTMX/Jinja2 is
the preferred next server-rendered option only if the dashboard needs a production-oriented UI;
React/Next.js requires materially richer client or public-site needs.

**Rationale**: HTMX keeps the server as source of truth without a JS build pipeline. React/Next.js adopted only when UX complexity or SEO requirements justify it.

[→ ADR 003](adr/003-htmx-vs-react.md)

---

### 004: Docker BuildKit & Security Scanning

**Decision**: BuildKit with cache mounts for 3-5x faster rebuilds; Trivy + pip-audit for scanning.

**Rationale**: BuildKit's `--mount=type=cache` persists apt/pip layers across builds. Trivy is free, fast, and integrates with GitHub Code Scanning via SARIF.

[→ ADR 004](adr/004-docker-buildkit-and-security-scanning.md)

---

### 005: GitHub OIDC vs Long-Lived Access Keys

**Decision**: GitHub OIDC for CI/CD authentication; no AWS access keys in GitHub Secrets.

**Rationale**: OIDC generates short-lived credentials per workflow run. Compromised tokens expire in minutes. Full CloudTrail audit trail of every role assumption.

*(ADR 005 not yet written up — this entry predates the ADR file existing.)*

---

### 006: Terraform S3 Backend vs Local State

**Decision**: S3 backend + native lockfile locking (Terraform >= 1.9).

**Rationale**: Remote state with versioning enables audit trail and team collaboration. Lockfile locking eliminates DynamoDB dependency.

*(ADR 006 not yet written up — this entry predates the ADR file existing.)*

---

### 007: Migration Runner vs Sidecar

**Decision**: In-process migration runner at startup; not a separate init container or sidecar.

**Rationale**: Simpler deployment (no extra container), Alembic runs in the same process as the app, fail-fast on migration errors.

[→ ADR 007](adr/007-migration-runner-vs-sidecar.md)

---

### 008: EC2/Compose vs ECS Fargate vs EKS

**Decision**: EC2 plus Docker Compose is the AWS Stage 0 target. ECS Fargate and EKS remain later
stages triggered by independent scaling or deployment evidence.

**Rationale**: Stage 0 preserves the locally exercised operating model and has fewer moving parts.
ECS can remove host operations later; EKS is justified only by Kubernetes-specific requirements.

*(ADR 008 not yet written up — this entry predates the ADR file existing.)*

---

### 012: LangGraph Agent Architecture

**Decision**: LangGraph StateGraph with Anthropic model roles for classification and drafted
analysis, PostgreSQL checkpointing, and a required human-review pause before notification.

**Rationale**: LangGraph makes state transitions and pause/resume explicit. The agent is optional and
fail-open; deterministic incident behavior and offline evaluation do not depend on provider access.

[→ ADR 012](adr/012-langgraph-agent.md)

---

### 014: Management Plane vs Ops Plane

**Decision**: Separate management plane (app-level RBAC, tenant admin) from ops plane (infrastructure, observability access).

**Rationale**: Clear separation of concerns between product administrators and SRE/DevOps roles. Each plane has independent auth boundaries.

[→ ADR 014](adr/014-management-vs-ops-plane.md)

---

## Quick Reference Decision Matrix

| Question | Answer |
| -------- | ------ |
| I/O-bound or CPU-bound? | I/O → async; CPU → processes |
| API framework? | FastAPI (async JSON) / Django (full-stack) / Flask (simple) |
| Primary DB? | PostgreSQL almost always; MongoDB for genuinely varied document shapes |
| ORM vs raw SQL? | ORM for CRUD; raw SQL for analytics |
| Cache or not? | Only after measuring; fail-open pattern |
| Message broker? | Redpanda (learning/dev); managed Kafka only after a measured production need |
| Vector store? | pgvector (existing Postgres, <10M); Qdrant (scale + dedicated) |
| Frontend? | Streamlit now; HTMX for a server-rendered ops UI; React only for complex client state |
| Cloud compute? | EC2 + Compose Stage 0; ECS/EKS only after explicit triggers |
| Cloud database? | RDS PostgreSQL (cost); Aurora (HA + replicas, 3x cost) |
| Cloud cache? | ElastiCache Cache (persistent); Memcached (simple, fast) |
| Cloud message queue? | MSK Serverless (managed, IAM auth); self-managed Kafka (control) |
| Infrastructure code? | Terraform (popular, HCL); CloudFormation (AWS-native, verbose) |
| Terraform state? | Remote S3 + lockfile (team-safe); local (solo, risky) |
| CI/CD secrets? | GitHub OIDC (no AWS keys, audit trail); AWS access keys (simple, risky) |
| Auth? | JWT (stateless, multi-service); Sessions (need immediate revocation) |
| Distributed txn? | Saga pattern (event choreography) |
| Schema migrations? | Alembic (production); `create_all()` (tests only) |
| Docker build system? | BuildKit with cache mounts (fast rebuilds); Legacy builder (simple) |
| Base image pinning? | Digest pinning (reproducible); version tags (auto-patch) |
| Container scanning? | Trivy (free, fast); Snyk (managed, compliance) |
| Dependency scanning? | pip-audit (Python CVEs); Bandit (code security issues) |
| Security gates? | Pre-commit hooks (local); GHA CI/CD (automated verification) |
