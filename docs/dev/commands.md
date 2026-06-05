# Commands Reference

Track: B — Engineering Execution

All CLI commands for daily development, testing, migrations, and infrastructure.
Use Ctrl+F to jump to any section.

---

## Daily Development

```bash
# First command on a new machine/session
just doctor
```

`just doctor` verifies host requirements and prepares `.local-dev/` folders for raw dumps, verbose
responses, traceback captures, and local logs.

### Start Services

Two modes depending on whether you want the app container running or the app running locally:

```bash
# Mode 1: full MVP stack (db, redis, redpanda, ingestor, dashboard)
just up

# Mode 1 + HTTPS parity (requires certs — run 02-setup-local-https.sh first):
just up-https   # includes nginx on :443

# Mode 2: infra only — use when running uvicorn directly outside Docker
docker compose up -d db redis redpanda
# then in a second terminal:
uv run uvicorn services/ingestor/main:app --reload

# Stop all:
just down

# Stop nginx specifically (keeps core services running):
just down-https
```

### Run Dev Server (no Docker)

```bash
uv sync
uv run uvicorn services/ingestor/main:app --reload
uv run uvicorn services/ingestor/main:app --reload --port 8001
```

### Health Check

```bash
# Direct (HTTP):
curl http://localhost:8000/health
curl http://localhost:8000/readyz
curl http://localhost:8000/metrics



just api-check   # fails fast if stack is not ready
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
docker compose exec db psql -U postgres -d api_observatory
psql "postgresql://postgres:postgres@localhost:5432/api_observatory"
```

### Useful psql Commands

```sql
\dt
\d observations
SELECT pid, usename, state FROM pg_stat_activity;
EXPLAIN ANALYZE SELECT * FROM observations WHERE source_id = 1 LIMIT 10;
```

### Redis

```bash
docker compose exec redis redis-cli
docker compose exec redis redis-cli KEYS "*"
docker compose exec redis redis-cli FLUSHALL   # dev only
docker compose exec redis redis-cli MONITOR
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
# Create default admin user (201 on first run, 409 if already exists — both OK)
just create-admin

# Seed one demo source (required by contracts tests — creates source_id=1)
just seed-source

# Seed three demo sources for probe/scorecard/drift workflows
just seed-demo

# Seed one healthy + one failing source for probe contrast demo
just seed-probes
```

---

## API Testing

### Bruno (end-to-end)

```bash
# Full E2E cycle: db-reset → create-admin → seed-source → Bruno collections
just api-test

# Run Bruno manually
cd bruno && bru run . -r --env local
```

### curl — Auth

```bash
# Direct HTTP:
TOKEN=$(curl -sf -X POST http://localhost:8000/api/v1/auth/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=admin&password=admin123' | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/scorecards
```

### curl — Core Resources

```bash
# Sources
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/sources
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/sources/1/health

# Scorecards
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/api/v1/scorecards?limit=20"
curl -k -H "Authorization: Bearer $TOKEN" "https://localhost/api/v1/scorecards?limit=20"

# Drift events
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/contracts/sources/1/drift-events

# Agent enrichment
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/agent/enrich/1
```

### OpenAPI

```bash
# Direct (HTTP):
open http://localhost:8000/docs
curl http://localhost:8000/openapi.json

open https://localhost/api/docs
curl https://localhost/api/openapi.json
```

---

## Tests

```bash
# Unit only (no DB, no Docker)
just test-unit
uv run pytest -m unit -q

# Integration (Postgres + Redis via testcontainers)
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
# Raw Prometheus metrics
curl http://localhost:8000/metrics

# Logs
docker compose logs ingestor -f
docker compose logs ingestor -f | grep '"level":"ERROR"'
docker compose logs ingestor | grep '"cid":"<value>"'
```

---

## Load Testing
---

## Infrastructure & Sandbox (Floci)

### One-Time AWS Profile Setup

```bash
# ~/.aws/credentials
[sandbox]
aws_access_key_id     = test
aws_secret_access_key = test

# ~/.aws/config
[profile sandbox]
region = us-east-1
```

See [docs/setup/sandbox-aws-profile.md](../setup/sandbox-aws-profile.md).

### Sandbox Workflow

```bash
# Terminal 1 — start Floci + infra
just sandbox-up

# Terminal 2 — migrate + start uvicorn with Floci env
just sandbox-dev

# Terminal 1 (after ingestor is up) — seed data
just sandbox-seed
```

### Sandbox Tests

```bash
just sandbox   # Floci + infra + AWS integration tests
```

### Terraform

```bash
just tf-init    # init backend (auto-detects sandbox or dev)
just tf-plan    # validate + plan
just tf-apply   # apply (runs tf-plan first)
just tf-destroy # destroy all resources
just tf-fresh   # init → plan → apply

# Real AWS:
TF_ENV=dev just tf-plan
TF_ENV=dev just tf-apply
```

---

## Git & Conventional Commits

```bash
git commit -m "feat(sources): add probe interval override"
git commit -m "fix(agent): handle empty classification response"
git commit -m "docs(commands): align with MVP justfile"
git commit -m "chore(deps): bump httpx to 0.28"
# Types: feat, fix, docs, style, refactor, test, chore, perf, ci
```
