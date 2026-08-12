# ADR 015: `inference` Gets a Dedicated pgvector Postgres Instance

## Status

Accepted (2026-07-11). Supersedes the earlier Qdrant evaluation.

## Context

Phase 2 of the AI-augmented observatory plan
(`docs/.plans/ai-augmented-observatory-agent-mcp.md`) built `services/inference/` — embeddings +
semantic search for RAG, backed by pgvector. The first cut shared the ingestor's `ingestor-db` Postgres
instance (separate schema, separate Alembic migration history, but one physical container).

Revisiting that shortly after: should `inference` get its own dedicated Postgres instance instead
of sharing one? And separately — `docs/03-planning/mvp-roadmap.md` cites an older decision,
ADR 002, which chose "Qdrant primary, pgvector secondary." Investigating that ADR found it was
written for an earlier, larger 8-phase "Data Zoo Platform" design that predates this project's
current MVP scope (its own "Part of" link points at a doc that only exists in
`docs/_archive/`) — it was never archived or superseded when the project pivoted, so it's stale
documentation debt, not a live constraint.

The current deployment-relevant constraint is an inexpensive, temporary AWS MVP exercise on
EC2. The exact instance size is an infra decision and no cloud deployment is claimed. Resource
cost remains a design constraint, not a permanent ceiling.

## Decision

`inference` is a separately deployed FastAPI service with its own PostgreSQL container
(`inference-db`), own migrations, own Dockerfile, and own embedding model (`fastembed` +
`BAAI/bge-small-en-v1.5`). The ingestor calls it over HTTP for embeddings. If the service is
down, vector-search endpoints return 503 but core CRUD is unaffected.

`inference-db` uses the same pgvector-enabled image as `ingestor-db` (`infra/database/Dockerfile`),
with own volume, own credentials (`API_OBS_INFERENCE_DB_PASSWORD`), and own port (`5433`).
**No Qdrant, today.**

### Service-boundary rationale

- **Separation of concerns**: The ingestor handles observation CRUD, scheduling, auth, and
  notifications. The inference service handles embedding generation and vector search. Mixing
  them would couple two independently scalable workloads.
- **Resource isolation**: Embedding models consume significant RAM and CPU. Keeping them in a
  separate process prevents the ingestor's API workers from being starved by model inference.
- **Failure isolation**: If the inference service crashes or the model download fails, the
  ingestor continues serving observations. Vector search degrades gracefully (503) rather than
  taking down the entire API.
- **Independent deployment**: The inference service can be updated, scaled, or replaced without
  redeploying the ingestor. This matters for a portfolio project because it demonstrates
  microservice awareness even in a Compose-based local stack.

### Database options considered

- **Shared pgvector** (Phase 2's original shape): simplest, lowest resource cost, but couples two
  independently-deployable services to one physical database process — a real service-boundary
  gap, not just a style preference (an `ingestor-db` outage/maintenance/backup-restore now blocks
  `inference` too, and vice versa).
- **Dedicated pgvector** (chosen): same engine/ops model as `ingestor-db` (no new tooling to learn/monitor),
  keeps one database engine and a small second Postgres process holding only
  `indexed_documents`), and gives real per-service database ownership.
- **Qdrant** (deferred, not rejected): the reasoning ADR 002 originally gave — HNSW performance,
  "you learn two distinct data models," genuine portfolio/interview value — is still valid on its
  own terms. It's deferred because it isn't justified by a concrete capability need yet (current
  data volumes are nowhere near where pgvector's IVFFlat/HNSW indexes become the bottleneck ADR 002
  cited), and it adds real operational cost ADR 002 itself flagged: a second database *engine* to
  monitor/back up, and eventual-consistency sync between Postgres and Qdrant. This is independent
  of a specific VM budget — even with more memory, Qdrant would still
  need a concrete reason to adopt beyond "budget now allows it."
- **Qdrant, local-dev-only profile**: floated as a middle ground (get the portfolio value without
  deploying it to the demo VM) but rejected for now as a scope increase — two vector-store code
  paths to maintain — without a concrete near-term payoff.

## Consequences

### Positive

- Real per-service database ownership — `inference` doesn't depend on `ingestor-db`'s availability/schema
  changes, and vice versa. A clean "each microservice owns its own datastore" story.
- No new tooling: same Postgres image, same migration tooling (Alembic), same backup/restore
  playbook as `ingestor-db` — zero new operational surface area.
- Fits the current local and low-cost MVP direction; doesn't foreclose Qdrant later if a concrete
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
