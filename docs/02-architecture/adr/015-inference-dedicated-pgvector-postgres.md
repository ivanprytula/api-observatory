# ADR 015: `inference` Gets a Dedicated pgvector Postgres Instance

## Status

Accepted (2026-07-11). Supersedes [ADR 002](002-qdrant-vs-pgvector.md) (orphaned — see that
file's stub for why).

## Context

Phase 2 of the AI-augmented observatory plan
(`docs/.plans/ai-augmented-observatory-agent-mcp.md`) built `services/inference/` — embeddings +
semantic search for RAG, backed by pgvector. The first cut shared the ingestor's `db` Postgres
instance (separate schema, separate Alembic migration history, but one physical container).

Revisiting that shortly after: should `inference` get its own dedicated Postgres instance instead
of sharing one? And separately — `docs/03-planning/mvp-roadmap.md` cites an older decision,
ADR 002, which chose "Qdrant primary, pgvector secondary." Investigating that ADR found it was
written for an earlier, larger 8-phase "Data Zoo Platform" design that predates this project's
current MVP scope (its own "Part of" link points at a doc that only exists in
`docs/_archive/`) — it was never archived or superseded when the project pivoted, so it's stale
documentation debt, not a live constraint.

The actual deployment-relevant constraint today is [ADR 009](009-azure-free-tier-over-aws.md):
the default target is an Azure `Standard_B1s` VM — 1 vCPU, 1 GB RAM. That said, a paid tier is on
the table going forward if needed, so this is a default-budget constraint, not a hard permanent
ceiling.

## Decision

`inference` gets its own dedicated Postgres container (`inference-db` in `docker-compose.yml`),
same pgvector-enabled image as the existing `db` service (`infra/database/Dockerfile`), own
volume, own credentials (`INFERENCE_DB_PASSWORD`), own port (`5433`). **No Qdrant, today.**

### Options considered

- **Shared pgvector** (Phase 2's original shape): simplest, lowest resource cost, but couples two
  independently-deployable services to one physical database process — a real service-boundary
  gap, not just a style preference (a `db` outage/maintenance/backup-restore now blocks
  `inference` too, and vice versa).
- **Dedicated pgvector** (chosen): same engine/ops model as `db` (no new tooling to learn/monitor),
  fits comfortably in the B1s budget (~50-100MB idle for a second lightweight Postgres holding only
  `indexed_documents`), and gives real per-service database ownership.
- **Qdrant** (deferred, not rejected): the reasoning ADR 002 originally gave — HNSW performance,
  "you learn two distinct data models," genuine portfolio/interview value — is still valid on its
  own terms. It's deferred because it isn't justified by a concrete capability need yet (current
  data volumes are nowhere near where pgvector's IVFFlat/HNSW indexes become the bottleneck ADR 002
  cited), and it adds real operational cost ADR 002 itself flagged: a second database *engine* to
  monitor/back up, and eventual-consistency sync between Postgres and Qdrant. This is independent
  of the B1s RAM budget — even with a paid tier removing the resource ceiling, Qdrant would still
  need a concrete reason to adopt beyond "budget now allows it."
- **Qdrant, local-dev-only profile**: floated as a middle ground (get the portfolio value without
  deploying it to the demo VM) but rejected for now as a scope increase — two vector-store code
  paths to maintain — without a concrete near-term payoff.

## Consequences

### Positive

- Real per-service database ownership — `inference` doesn't depend on `db`'s availability/schema
  changes, and vice versa. A clean "each microservice owns its own datastore" story.
- No new tooling: same Postgres image, same migration tooling (Alembic), same backup/restore
  playbook as `db` — zero new operational surface area.
- Fits comfortably within the current B1s budget; doesn't foreclose Qdrant later if a concrete
  need emerges.

### Negative

- A second Postgres process to run/monitor (mitigated: same tooling as the first, lightweight
  resource footprint — this DB only ever holds `indexed_documents`).
- Two `DATABASE_URL`s to keep straight in local dev / deployment config instead of one.

### Neutral

- Qdrant remains a legitimate future ADR if/when there's a concrete reason (real scale, a specific
  feature only Qdrant offers) — not gated on budget alone, since budget is no longer the hard
  constraint it was assumed to be.

## Future Path

Revisit if `indexed_documents` grows into the range where pgvector's index strategy genuinely
becomes a bottleneck (ADR 002's own cited threshold: >100K vectors), or if a specific Qdrant
capability (standalone scaling, a particular index type) becomes a concrete requirement — not
before.
