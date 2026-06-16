# Monorepo Structure

Track: C — Architecture and Platform Strategy


Single-repository, multi-service Python monorepo. One `uv.lock`, one `pyproject.toml`
for tooling, six independently deployable services.

## Repository Layout

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

## Why a Monorepo?

- **One `uv.lock`** — reproducible, deterministic builds across all services and CI.
  Upgrades are intentional: run `uv lock --upgrade` locally, test, then commit.
- **Shared tooling** — Ruff, ty, pytest, coverage, and all dev dependencies live in one
  `pyproject.toml`. No per-service tool drift.
- **Atomic commits** — a single PR can update a shared contract schema, the service
  that produces it, and the service that consumes it — all at once.
- **Single CI pipeline** — change-impact routing (`dorny/paths-filter`) triggers only
  the jobs relevant to what changed.

## Why `alembic/` Stays at Root

Alembic manages the ingestor's PostgreSQL schema and runs at deploy time against the
live database. It stays at the repo root because:

1. It depends on `services/ingestor/models.py`, `services/ingestor/database.py`, and
   `services/ingestor/config.py` — all ingestor internals.
2. Migration history (`alembic/versions/`) is linear and shared with CI; moving it
   inside the service directory would break the `alembic.ini` `script_location` and
   all existing relative paths.
3. The migration runner (`uv run alembic upgrade head`) is a root-level concern at
   deploy time, not a service-internal concern.

If `ingestor` is ever extracted to its own repository, `alembic/` travels with it.

## Service Boundaries

Services communicate exclusively over the network (HTTP, Kafka). Python imports across
service boundaries are **forbidden** and enforced at CI time:

```bash
uv run python scripts/ci/check_service_boundaries.py
```

The two permitted cross-cutting namespaces are `libs.contracts` and `libs.platform`.
Any other cross-service Python import is a CI violation (SVC001/SVC002/SVC003).

### Co-located Tests

Each service owns its tests under `services/<name>/tests/`. These are regular pytest
test modules that import only from their own service. The boundary scanner scans these
files but treats same-service imports as permitted (owner == target — no violation).

Root `tests/` holds only:

- `conftest.py` — shared fixtures (e.g. `apply_migrations`)
- `shared/` — reusable payloads and factory helpers
- `e2e/` — cross-service end-to-end tests
- `integration/schema/` — schema integrity tests that span services

## Adding a New Service

1. Create `services/<name>/` with at minimum:
   - `__init__.py`
   - `main.py` (FastAPI app)
   - `pyproject.toml` (namespace marker with `[project]` metadata, `dependencies = []`)
   - `Dockerfile`
   - `README.md` (port, env vars, spin-up command, test command)
2. Add to `SERVICE_ROOTS` in `scripts/ci/check_service_boundaries.py`.
3. Add path-filter entry and matrix include in `.github/workflows/ci.yml`.
4. Add ownership line to `.github/CODEOWNERS`.
5. Add service to `docker-compose.yml` with health check and develop.watch.

## Extracting a Service to Its Own Repository

When a service needs independent deploy cadence or team ownership:

1. Copy `services/<name>/` and its `services/<name>/tests/` into the new repo.
2. Copy relevant `libs/` dependencies or publish them as packages.
3. Copy `alembic/` if the service owns the schema (currently only `ingestor`).
4. Copy the per-service sections from root `pyproject.toml` (pytest markers, coverage).
5. Set up its own `uv.lock` with `uv lock`.
6. Remove from this monorepo in a single atomic commit (update `SERVICE_ROOTS`,
   `CODEOWNERS`, `ci.yml`, `docker-compose.yml`).

## Dependency Lock Strategy

| Layer | File | Role |
|-------|------|------|
| Intent | `pyproject.toml` | `>=` version ranges |
| Fact | `uv.lock` | Exact pins, committed to repo |
| Build | `uv sync --frozen` | All CI and Docker builds read from lock |

Never regenerate `uv.lock` in CI. Upgrades are always intentional local operations:

```bash
uv lock --upgrade    # bump all, or --upgrade-package <name> for one
# test thoroughly, then:
git add uv.lock && git commit -m "chore: update dependencies"
```
