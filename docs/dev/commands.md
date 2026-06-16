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

### Local URLs

| Mode | API base | API docs | Dashboard |
|---|---|---|---|
| Direct HTTP | `http://127.0.0.1:8000` | `http://127.0.0.1:8000/docs` | `http://127.0.0.1:8501` |
| Edge HTTPS | `https://127.0.0.1/api` | `https://127.0.0.1/api/docs` | `https://127.0.0.1/` |

Prefix commands with `LOCAL_API_SCHEME=https` to switch to edge proxy mode.

### Start Services

Two modes depending on whether you want the app container running or the app running locally:

```bash
# Mode 1: full MVP stack (db, cache, broker, ingestor, dashboard)
just up

# Mode 1 + HTTPS parity (requires certs — run scripts/setup/02-setup-local-https.sh first):
just up-https   # includes edge on :443; LOCAL_API_SCHEME=https for API clients

# Mode 2: infra only — use when running uvicorn directly outside Docker
docker compose up -d db cache broker
# then in a second terminal:
uv run uvicorn services/ingestor/main:app --reload

# Stop all:
just down

# Stop edge specifically (keeps core services running):
just down-https
```

### Run Dev Server (no Docker)

```bash
uv sync
uv run uvicorn services.ingestor.main:app --reload
uv run uvicorn services.ingestor.main:app --reload --port 8001
```

### Health Check

```bash
# Quick check (uses local-url.sh under the hood):
just api-check

# Manual equivalent:
curl -sf http://127.0.0.1:8000/health
curl -sf http://127.0.0.1:8000/readyz
curl -sf http://127.0.0.1:8000/metrics
```

## Database Management

```bash
# Apply all pending migrations
just migrate

# Full DB wipe → restart → migrate → wait for readiness
just db-reset
```

### Connect to PostgreSQL

```bash
# Safe wrapper — blocks accidental prod/RDS connections
just psql-safe

# Direct (local only)
docker compose exec db psql -U postgres -d api_observatory
psql "postgresql://postgres:postgres@127.0.0.1:5432/api_observatory"
```

### Useful psql Commands

```sql
\d observations
SELECT pid, usename, state FROM pg_stat_activity;

-- EXPLAIN ANALYZE is opt-in: set ALLOW_EXPLAIN_ANALYZE=true in test env only.
-- Never run EXPLAIN ANALYZE against remote/staging/prod RDS — it causes full table scans.
-- For local curiosity: EXPLAIN (FORMAT JSON) SELECT ... WHERE source_id = 1 LIMIT 10;
```

### Cache

```bash
docker compose exec cache redis-cli
docker compose exec cache redis-cli KEYS "*"
docker compose exec cache redis-cli FLUSHALL   # dev only
docker compose exec cache redis-cli MONITOR
```

---

## Migrations (Alembic)

```bash
uv run alembic current
uv run alembic history --verbose
uv run alembic upgrade head
uv run alembic upgrade +1
uv run alembic downgrade -1
uv run alembic downgrade <revision-id>
uv run alembic revision --autogenerate -m "add_column_to_sources"
uv run alembic revision -m "create_indexes_on_observations"
uv run alembic upgrade head --sql   # dry-run
```

> **Gotcha:** Python 3.14 + Alembic requires `sqlalchemy[asyncio]` in deps.
> See [docs/dev/gotchas.md](gotchas.md) for details.

---

## Seeding

```bash
# Print copy-pasteable curl commands for manual bootstrap
just init

# Or auto-seed admin + demo sources (headless):
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

### curl — Auth

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=admin&password=admin123' | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/scorecards
```

### curl — Core Resources

```bash
BASE=http://127.0.0.1:8000
AUTH="Authorization: Bearer $TOKEN"

curl -H "$AUTH" "$BASE/api/v1/sources"
curl -H "$AUTH" "$BASE/api/v1/sources/1/health"
curl -H "$AUTH" "$BASE/api/v1/scorecards?limit=20"
curl -H "$AUTH" "$BASE/api/v1/contracts/sources/1/drift-events"
curl -X POST -H "$AUTH" "$BASE/api/v1/agent/enrich/1"
```

### OpenAPI

```bash
curl http://127.0.0.1:8000/openapi.json
# Or visit http://127.0.0.1:8000/docs in a browser
```

---

## Tests

```bash
# Unit only (no DB, no Docker)
just test-unit
uv run pytest -m unit -q

# Integration (Postgres + Cache via testcontainers)
just test-integration
uv run pytest -m integration -q

# E2E (full stack required)
just test-e2e
uv run pytest -m e2e -q

# Stop on first failure
uv run pytest -x

# Specific file or test
uv run pytest tests/test_observations.py::test_create_observation -xvs
```

### Coverage

```bash
uv run pytest tests/ --cov=services/ingestor --cov-report=term-missing
uv run pytest tests/ --cov=services/ingestor --cov-report=html
uv run pytest tests/ --cov=services/ingestor --cov-fail-under=80
```

---

## Code Quality

```bash
uv run ruff check .
uv run ruff check . --fix
uv run ruff format .
uv run ruff format . --check   # CI mode

# Pre-commit
pre-commit install              # one-time
pre-commit run --all-files
pre-commit run ruff --all-files
```

---

## Docker & Release

```bash
# Build image
just docker-build-image                      # tag: api-observatory:local
just docker-build-image my-tag:v1.2.3

# Size audit
# Full deploy audit: build → size → scan
just deploy-audit
```

---

## Observability

```bash
curl http://127.0.0.1:8000/metrics
docker compose logs ingestor -f
docker compose logs ingestor -f | grep '"level":"ERROR"'
```

---

## Load Testing

---

## Infrastructure & Sandbox (Floci)

Use this section for the local AWS-shaped Floci sandbox. Prefer canonical
`floci-*` recipes; older `sandbox-*` aliases still exist for compatibility but
are not the recommended docs surface.

### One-Time AWS Profile Setup

```bash
# ~/.aws/credentials
[sandbox]
aws_access_key_id     = test
aws_secret_access_key = test

# ~/.aws/config
[profile sandbox]
region = eu-central-1
```

See [docs/setup/sandbox-aws-profile.md](../setup/sandbox-aws-profile.md).

### Floci Workflow

```bash
# Start Floci, seed S3/SQS, start Compose infra, migrate, and seed admin/demo
just floci-up

# Start uvicorn locally with Floci-shaped AWS env
just floci-dev

# Validate Floci health, S3, SQS, and optional API health
just floci-validate

# Run Floci-specific E2E tests
just floci-test

# Stop Floci only; Compose data-plane can keep running
just floci-down
```

`just floci-up` already creates the local S3 bucket and SQS queue and seeds
admin/demo data. Use `just create-admin`, `just seed-demo`, or
`just seed-source` only for targeted local resets.

### Terraform

```bash
# Sandbox/Floci Terraform
just tf init          # init backend once per terminal session
TF_ENV=sandbox just tf plan
TF_ENV=sandbox just tf apply
TF_ENV=sandbox just tf show

# Full reset: init → plan → apply
TF_ENV=sandbox just tf fresh

# Real AWS dev Terraform
TF_ENV=dev just tf plan
TF_ENV=dev just tf apply
```

`just tf apply` applies the saved plan from `just tf plan`; it does not run a
fresh plan first. Use `just tf fresh` when you want init → plan → apply in one
sequence.

### Floci Deploy

```bash
# Build, push, and deploy to Floci-backed ECS after Terraform has created ECS resources
just floci-deploy
```

### Compatibility Aliases

These aliases still run, but new docs should prefer the canonical name on the right:

| Compatibility alias | Canonical recipe |
|---|---|
| `just sandbox-up` | `just floci-up` |
| `just sandbox-down` | `just floci-down` |
| `just sandbox-reset` | `just floci-reset` |
| `just sandbox-dev` | `just floci-dev` |
| `just sandbox` | `just floci-test` |
| `just sandbox-deploy` | `just floci-deploy` |

### Stack Awareness

Use `just stack-info` to print the active backend stack from env vars and Docker state.
Call it from `just up`, `just dev`, or `just floci-dev` to get an immediate banner:

```bash
=== STACK SUMMARY ===
  Cloud backend   : Local-Docker | Floci (…)| AWS (profile=…)
  Terraform env   : sandbox | dev
  Postgres        : Local-Compose-Postgres | External (host=…)
  Cache           : redis://cache:6379 | unset
  BROKER_URL: broker:29092 | unset
  MinIO endpoint  : 127.0.0.1:9000 | unset
  INGESTOR_URL    : http://127.0.0.1:8000
======================
```

### Environment variable matrix (quick reference)

| Variable | local-docker | sandbox | dev | prod |
|---|---|---|---|---|
| `ENVIRONMENT` | `development` | `development` | `development` | `production` |
| `DATABASE_URL` | Compose-injected | Compose-injected | AWS RDS DSN | AWS RDS DSN |
| `CACHE_URL` | `redis://cache:6379` | `redis://cache:6379` | ElastiCache endpoint | ElastiCache endpoint |
| `BROKER_URL` | `broker:29092` | `broker:29092` | MSK bootstrap | MSK bootstrap |
| `LOG_FORMAT` | `json` | `json` | `json` | `json` |
| `AWS_PROFILE` | unset | `sandbox` | named dev profile | prod profile |
| `AWS_ENDPOINT_URL` | unset | `http://127.0.0.1:4566` | unset | unset |

### Data movement recipes

```bash
# Dump local Compose DB → timestamped .sql
just pg-dump

# Restore into local Compose DB (drops schema first)
just pg-restore .local-dev/dumps/api-observatory-20260101-120000.sql

# Pull a gzipped dump from S3 and restore into local Compose DB
just pg-restore-from-s3 s3://api-observatory-local/dumps/prod-snapshot.sql.gz

# Mirror S3 bucket to local dir (Floci or real AWS)
just s3-dump-local bucket=api-observatory-local dest=.local-dev/dumps/s3-20260101

# Upload local dir to S3
just s3-restore-to-remote bucket=api-observatory-local src=.local-dev/dumps/s3-20260101
```

### Safety guards

- `just psql-safe` (default target `db`) blocks connections to `*.rds.amazonaws.com` or `*.amazonaws.com` hostnames.
- `EXPLAIN ANALYZE` integration tests skip by default; opt in with `ALLOW_EXPLAIN_ANALYZE=true` only against local Postgres.
- Never run `EXPLAIN ANALYZE` against remote RDS — it executes queries synchronously on the production compute.

---

## Git & Conventional Commits

```bash
git commit -m "feat(sources): add probe interval override"
git commit -m "fix(agent): handle empty classification response"
git commit -m "docs(commands): align with MVP justfile"
git commit -m "chore(deps): bump httpx to 0.28"
# Types: feat, fix, docs, style, refactor, test, chore, perf, ci
```
