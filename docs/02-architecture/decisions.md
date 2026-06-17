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

**Decision**: Redpanda (Kafka-compatible, no Zookeeper) for local dev; MSK Serverless for AWS prod.

**Rationale**: Redpanda gives Kafka wire-protocol compatibility with a single binary (no Zookeeper). The event-log model (replay from any offset) enables CQRS read models. Switch to MSK Serverless in prod uses the same `aiokafka` code.

[→ ADR 001](adr/001-kafka-vs-rabbitmq.md)

---

### 002: Qdrant vs pgvector — Vector Database

**Decision**: Qdrant primary (teaches dedicated vector DB ops); pgvector added in Phase 5 for comparison.

**Rationale**: Qdrant teaches the dedicated vector DB model (collections, HNSW indexing, payload filtering). pgvector is simpler but slower at scale (>10M vectors).

[→ ADR 002](adr/002-qdrant-vs-pgvector.md)

---

### 003: HTMX vs React — Frontend Framework

**Decision**: HTMX + Jinja2 for ops/admin workflows; React/Vite for rich client interaction; Next.js for SEO/public pages.

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

[→ ADR 005](adr/005-github-oidc-vs-long-lived-keys.md)

---

### 006: Terraform S3 Backend vs Local State

**Decision**: S3 backend + native lockfile locking (Terraform >= 1.9).

**Rationale**: Remote state with versioning enables audit trail and team collaboration. Lockfile locking eliminates DynamoDB dependency.

[→ ADR 006](adr/006-terraform-s3-backend-vs-local.md)

---

### 007: Migration Runner vs Sidecar

**Decision**: In-process migration runner at startup; not a separate init container or sidecar.

**Rationale**: Simpler deployment (no extra container), Alembic runs in the same process as the app, fail-fast on migration errors.

[→ ADR 007](adr/007-migration-runner-vs-sidecar.md)

---

### 008: ECS Fargate vs EKS

**Decision**: ECS Fargate for this project scale (1-10 microservices).

**Rationale**: ECS Fargate eliminates Kubernetes control-plane operations. Cost-optimized for small-to-medium service counts. Kubernetes is a separate learning path.

[→ ADR 008](adr/008-ecs-fargate-vs-eks.md)

---

### 012: LangGraph Agent Architecture

**Decision**: LangGraph StateGraph with dual-model routing (gpt-4o-mini for classify, gpt-4o for deep analysis).

**Rationale**: LangGraph gives structured state-machine control over agent flow. Dual-model routing saves ~10x cost by using the cheap model for 90% of calls.

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
| Message broker? | Redpanda (learning/dev); MSK (prod) |
| Vector store? | pgvector (existing Postgres, <10M); Qdrant (scale + dedicated) |
| Frontend? | HTMX (backend devs, server-rendered); React (complex SPA) |
| Cloud compute? | ECS Fargate (managed, learning); EKS (K8s expertise required) |
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
