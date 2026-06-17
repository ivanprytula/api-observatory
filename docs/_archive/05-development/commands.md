# Commands Reference

Track: B — Engineering Execution

Single command reference for daily development, testing, migrations, and infrastructure.

The `Justfile` is the source of truth for recipe names, arguments, and behavior.
Run `just --list --unsorted` from the repo root for the live recipe list.

Prefer canonical recipe names in new docs. Compatibility aliases such as
`sandbox-up` still exist, but Floci workflows should document `floci-*` names.
Workflow docs should link here instead of duplicating this catalog.

---

## Daily Development

```bash
# First command on a new machine/session
just doctor
```

`just doctor` verifies host requirements and prepares `.local-dev/` folders for raw dumps, verbose
responses, traceback captures, and local logs.

See the Local URL Matrix for the local URL table (Direct HTTP vs Edge HTTPS).

### Start Services

```bash
# Full MVP stack (db, cache, broker, ingestor, dashboard)
just up

# Full stack + HTTPS edge proxy (requires certs — run scripts/setup/02-setup-local-https.sh first)
just up-https

# Stop all:
just down

# Stop edge (keeps core services running):
just down-https
```

### Run Dev Server (no Docker)

```bash
uv sync
uv run uvicorn services.ingestor.main:app --reload
```

### Health Check

```bash
just api-check
```

---

## Database Management

```bash
# Apply all pending migrations
just migrate

# Full DB wipe → restart → migrate → wait for readiness
just db-reset

# Safe psql connection (blocks RDS connections)
just psql-safe
```

See [PostgreSQL psql docs](https://www.postgresql.org/docs/current/app-psql.html) for interactive commands.

---

## Seeding

```bash
# Print copy-pasteable curl commands for manual bootstrap
just init

# Auto-seed admin + demo sources (headless):
just _auto-init
```

---

## API Testing

### Bruno (end-to-end)

**Desktop:** Open `bruno/` in Bruno Desktop → select `local` env → run requests visually.

```bash
# CI / headless: full E2E cycle
just api-test

# Manual CLI run
BRUNO_BASE_URL="http://127.0.0.1:8000" \
  cd bruno && bru run . -r --env local --env-var "baseUrl=${BRUNO_BASE_URL}"
```

See `bruno/collections/` for all available API request examples.

### curl — Auth

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=admin&password=admin123' | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/scorecards
```

---

## Tests

```bash
# Unit only (no DB, no Docker)
just test-unit

# Integration (Postgres + Cache via testcontainers)
just test-integration

# E2E (full stack required)
just test-e2e
```

---

## Additional Operations

For operations not listed above, see these resources:

| Area | Resource |
|---|---|
| Coverage / code quality | `uv run pytest --cov=...`, `ruff check/fix/format`, `pre-commit run --all-files` |
| Docker & release | `just docker-build-image`, `just deploy-audit` — see `scripts/` |
| Observability | `curl .../metrics`, `docker compose logs -f` |
| Alembic migrations | `just migrate` — see [Alembic docs](https://alembic.sqlalchemy.org/) for advanced operations |
| Floci sandbox | `just floci-up/dev/validate/test/down` — see `scripts/` |
| Terraform | `just tf plan/apply` — see `infra/terraform/` |
| Data movement | `just pg-dump`, `just pg-restore`, `just s3-dump-local` — see `scripts/` |
| Git | Use [Conventional Commits](https://www.conventionalcommits.org/) — `feat:`, `fix:`, `docs:`, `chore:`, etc. |
