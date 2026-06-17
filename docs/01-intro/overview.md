# Project Overview

Track: A — Product and Onboarding

Start here for project scope, learning goals, and the fastest path through the documentation.

## What This Repository Is

Data Zoo is an async Python data-platform project focused on production-style backend engineering:

- event ingestion and processing
- reliability and observability patterns
- secure-by-default delivery workflows
- deployment and operations runbooks

It is designed as both a working system and a learning portfolio.

## Core Outcomes

- Learn by building with realistic architecture constraints.
- Practice production engineering patterns end to end.
- Keep decisions explicit through ADRs and design docs.
- Preserve reproducible workflows through scripts and canonical command references.

## Documentation Navigation

The canonical index is the root README.md (Documentation Map section).

Use this reading order for most contributors:

1. Setup — First-Time Setup
2. Daily Development
3. Commands
4. Architecture Overview

Terminology used across docs:

- Workflow intent and sequence: Daily Development
- Canonical command source: Commands

## Hiring and Interview Fast Path

For portfolio and interview review:

1. CV (personal)
2. Architecture Overview
3. Backend Concepts and Patterns
4. Interview Prep Middle Plus (personal)

## Current Status

Current prioritized roadmap is in the personal directory.

## Quick Start

For execution-first onboarding:

1. Run `just doctor`
2. Run bootstrap from First-Time Setup
3. Use workflow intent and sequence from Daily Development
4. Use exact commands from Commands

## Project Principles

- Keep command details centralized; avoid duplicating long command blocks.
- Keep strategy and runbooks separate.
- Keep local artifacts in `.local-dev` and out of git.
- Prefer explicit links to canonical docs instead of restating procedures.

---

## Monorepo Structure

Single-repository, multi-service Python monorepo. One `uv.lock`, one `pyproject.toml` for tooling, six independently deployable services.

### Repository Layout

```text
services/              # Microservices — each owns its own code, tests, and README
  ingestor/            # Write-side CQRS: REST API, scraping, Kafka publish
  analytics/           # Read-side CQRS: materialized views, query API
  inference/           # AI adapter: embeddings, vector search (Qdrant)
  processor/           # Kafka enrichment consumer
  dashboard/           # Server-rendered UI: Jinja2 + SSE
  webhook/             # Inbound webhook gateway: HMAC, idempotency, audit log
libs/                  # Shared code — imported by any service
  contracts/           # Pydantic schemas shared across service boundaries
  platform/            # Infrastructure helpers (logging, config base classes)
alembic/               # Database migrations (ingestor owns the write schema)
docs/                  # Documentation
infra/                 # Infrastructure-as-Code (Terraform, Kubernetes, edge)
scripts/               # CI scripts, daily workflows, setup automation
tests/                 # Shared fixtures, e2e, cross-service schema tests
docker-compose.yml     # Local dev: all services + dependencies
pyproject.toml         # Root: all deps + tooling config (single uv.lock)
uv.lock                # Pinned lock file — committed, never regenerated in CI
```

### Why a Monorepo?

- **One `uv.lock`** — reproducible builds across all services. Upgrades are intentional.
- **Shared tooling** — Ruff, pytest, coverage all in one `pyproject.toml`.
- **Atomic commits** — a single PR can update a shared contract, producer, and consumer.
- **Single CI pipeline** — change-impact routing triggers only relevant jobs.

### Service Boundaries

Services communicate exclusively over the network (HTTP, Kafka). Python imports across service boundaries are **forbidden** and enforced at CI time:

```bash
uv run python scripts/ci/check_service_boundaries.py
```

The two permitted cross-cutting namespaces are `libs.contracts` and `libs.platform`.

### Adding a New Service

1. Create `services/<name>/` with `__init__.py`, `main.py`, `pyproject.toml`, `Dockerfile`, `README.md`.
2. Add to `SERVICE_ROOTS` in `scripts/ci/check_service_boundaries.py`.
3. Add path-filter entry and matrix include in `.github/workflows/ci.yml`.
4. Add ownership line to `.github/CODEOWNERS`.
5. Add service to `docker-compose.yml` with health check.

### Dependency Lock Strategy

| Layer | File | Role |
|-------|------|------|
| Intent | `pyproject.toml` | `>=` version ranges |
| Fact | `uv.lock` | Exact pins, committed to repo |
| Build | `uv sync --frozen` | All CI and Docker builds read from lock |

Never regenerate `uv.lock` in CI. Upgrades are always intentional local operations.

---

## Versioning

A strict, simple scheme to avoid confusing fallbacks during development and CI/CD.

### Contracts Version (canonical)

- Source: `libs/contracts/VERSION` (required, e.g. `0.1.3`)

### Service Version (provenance)

Two sources, in order of precedence:

1. `SERVICE_VERSION` environment variable (recommended for CI/production). CI should set it during build:
   ```bash
   echo "SERVICE_VERSION=$(git describe --tags --always --dirty --abbrev=7)" >> $GITHUB_ENV
   ```
2. `VERSION` file at the repository root (local development convenience).

The code fails fast if neither source is present. Use SemVer; append `+g<short-sha>` for git bisect provenance.

---

## Domain Model

*The what and why of every persistent entity, in Domain-Driven Design terms.*

Code references: `services/ingestor/models.py`, `services/ingestor/api_schemas/`

### Bounded Contexts

```text
Source Registry        │  Reliability Monitoring
  SourceProfile        │    ProviderHealthSample
                       │    ProviderScorecard (computed)
───────────────────────┼──────────────────────────────
Contract Drift         │  Identity & Access
  ContractSnapshot     │    User
  DriftEvent           │    UserTenant / ApiKey
───────────────────────┼──────────────────────────────
Observation Ingestion  │  Security & Abuse
  Observation          │    SecurityAuditEvent
                       │    AbuseSignal
───────────────────────┴──────────────────────────────
Messaging Infrastructure (cross-cutting)
  ProcessedEvent · OutboxEvent · InboxConsumption
```

### Source Registry

**Aggregate Root: `SourceProfile`** — a registered external API or data source.

| Field | Meaning |
|-------|---------|
| `name` | Unique slug (e.g. `httpbin`, `payments-api`) |
| `base_url` | URL probe workers connect to |
| `health_check_path` | Path for liveness probes |
| `probe_interval_seconds` | How often to probe |
| `is_active` | Soft-disable without deletion |

Invariants: `name` is globally unique, `health_check_path` starts with `/`, `base_url` must be valid HTTP/HTTPS (no loopback — SSRF prevention).

### Reliability Monitoring

**`ProviderHealthSample`** — one probe result: did the source respond, how fast, with what HTTP status. Append-only.

**`ProviderScorecard`** (no ORM table — computed by SQL `PERCENTILE_CONT` query). Fields: `uptime_pct`, `p50_latency_ms`, `p95_latency_ms`, `error_budget_burn_rate`, `window_days`, `slo_target_pct`.

### Contract Drift

**`ContractSnapshot`** — point-in-time schema observation. SHA-256 fingerprint short-circuits diff when nothing changed.

**`DriftEvent`** — created when consecutive snapshots differ. Fields: `event_type` (breaking/non-breaking/none), `severity`, `added_fields`, `removed_fields`, `type_changed_fields`, `compatibility_score`.

### Observation Ingestion

**`Observation`** — inbound data point. `(source, timestamp)` unique constraint drives idempotent upsert. Tags are always lowercase. Source cannot be a loopback address. Timestamp cannot be in the future.

### Identity & Access

**`User`** — authentication principal with role-based access (viewer, writer, operator, tenant_admin, admin). `**UserTenant`** — many-to-many user-to-tenant mapping. **`ApiKey`** — tenant-scoped, scope-limited M2M auth with "show once" pattern.

### Security & Abuse

**`SecurityAuditEvent`** — append-only, hash-chained audit log. No UPDATE or DELETE by convention.

**`AbuseSignal`** — mutable operational finding with lifecycle: open → resolved.

### Messaging Infrastructure

**`ProcessedEvent`** — idempotent Kafka consumption tracking with DLQ routing. **`OutboxEvent`** — transactional outbox pattern for reliable Kafka publishing. **`InboxConsumption`** — consumer-side deduplication.

### Cross-Cutting

- **TimestampMixin**: `created_at`, `updated_at`, `deleted_at` on all mutable entities. Soft-delete everywhere.
- **tenant_id**: present on most entities for row-level tenancy. Enforced in repository layer and PostgreSQL RLS.

### Entity Relationships

```text
SourceProfile ──< ProviderHealthSample
SourceProfile ──< ContractSnapshot
ContractSnapshot ──< DriftEvent
User >──< UserTenant
User ──< ApiKey
Observation (standalone — source is a string, not a FK)
```

---

## Related Documents

- README.md — Documentation Map
- Environment / Stack Matrix — deployment scenarios and env vars
- System Setup — prerequisites and system-level requirements
- First-Time Setup — bootstrap flow
- Daily Development — workflow intent and sequence
- Commands — canonical command reference
- Cloud Deployment — deployment model and runbook
