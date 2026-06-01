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

### Start All Services

Two modes depending on whether you want the app container running or the app running locally:

```bash
# Mode 1: full app stack (app container + all infra) — matches README Quick Start
just up          # db, redis, redpanda, ingestor, mongodb
just sandbox-up  # + Floci local AWS (S3, SQS)

# Mode 2: infra only — use when running uvicorn directly outside Docker
bash scripts/daily/01-start-dev-services.sh  # db, redis, redpanda, mongodb, jaeger
# then in a second terminal:
uv run uvicorn services/ingestor/main:app --reload

# Stop all:
just down
```

### Run Dev Server (no Docker)

```bash
# Install deps
uv sync

# Start Uvicorn with auto-reload (requires Postgres running via Mode 2 above)
uv run uvicorn services/ingestor/main:app --reload

# With custom port
uv run uvicorn services/ingestor/main:app --reload --port 8001
```

### Health Check

```bash
curl http://localhost:8000/health
curl http://localhost:8000/metrics
```

### Gateway Smoke Tests (API Gateway 5.4)

Run these checks after `docker compose up -d` to validate the local Nginx gateway pathing and
basic route health.

```bash
# One-command automated smoke test
./scripts/testing/04-gateway-smoke.sh

# Optional custom gateway URL (if not localhost)
./scripts/testing/04-gateway-smoke.sh https://my-gateway.local
```

Equivalent manual checks:

```bash
# 1) Ensure compose model is valid before runtime checks
docker compose config >/tmp/compose.out && echo "compose-config-ok"

# 2) Gateway entrypoint responds over HTTPS (self-signed cert in local dev)
curl -k -I https://localhost/

# 3) Ingestor docs are reachable via gateway API prefix
curl -k -I https://localhost/api/docs

# 4) Analytics service health route is reachable through gateway routing
curl -k https://localhost/analytics/health

# 5) Request-ID is returned by gateway for API requests
curl -k -sSI https://localhost/api/docs | grep -i "x-request-id"
```

Expected outcomes:

- `compose-config-ok` is printed.
- HTTPS checks return `200` or `30x` (route-dependent).
- `/analytics/health` returns a healthy JSON/text response from the analytics service.
- `x-request-id` header is present for `/api/*` responses.

### Service Discovery Checks (Orchestrator DNS)

Validate that gateway upstream targets use orchestrator DNS/service names (not localhost or
container IP assumptions):

```bash
# One-command service discovery validation
./scripts/testing/05-service-discovery-dns.sh
```

What this verifies:

- `docker-compose.yml` is valid.
- Every Nginx upstream host maps to a Compose service name.
- No upstream host uses loopback (`localhost`, `127.x.x.x`).

### Architecture Principles Guard (Step 6)

Run a single-command architecture guard to verify bounded contexts, idempotency markers,
resilience primitives, SLO alert rules, and contract versioning artifacts:

```bash
./scripts/testing/06-architecture-principles-guard.sh
```

What this verifies:

- Service boundaries are enforced (`scripts/ci/check_service_boundaries.py`).
- `processed_events` idempotency key and index markers are present in models.
- Outbox/Inbox baseline artifacts are present (models, migration markers, repository helper, integration test).
- Retry and circuit-breaker primitives are present under `libs/platform`.
- SLO alert rules include latency and critical error-rate alerts.
- Contracts version/changelog artifacts exist, with optional diff-gate when `origin/main` is available.

Run focused Outbox/Inbox schema checks (6.2 hardening):

```bash
uv run pytest tests/integration/schema/test_schema_integrity.py -k "OutboxInboxSchema" -m postgresonly -q -o addopts=''
```

Run focused bulkhead/retry-budget checks (6.4 hardening):

```bash
uv run pytest services/ingestor/tests/unit/core/test_bulkhead_retry_budget.py -q -o addopts=''
```

---

## Migrations (Alembic)

```bash
# Show current revision applied to the DB
uv run alembic current

# Show full migration history
uv run alembic history --verbose

# Apply all pending migrations (upgrade to head)
uv run alembic upgrade head

# Apply one step forward
uv run alembic upgrade +1

# Rollback one step
uv run alembic downgrade -1

# Rollback to specific revision
uv run alembic downgrade <revision-id>

# Autogenerate migration from model diffs
uv run alembic revision --autogenerate -m "add_source_column_to_observations"

# Create blank migration (for manual edits)
uv run alembic revision -m "create_indexes_on_observations"

# Show the SQL without applying (dry run)
uv run alembic upgrade head --sql
```

> **Gotcha:** Python 3.14 + Alembic requires `sqlalchemy[asyncio]` in deps.
> See [docs/dev/gotchas.md — Alembic Migrations on Python 3.14 + SQLAlchemy Async](gotchas.md#gotcha-alembic-migrations-on-python-314--sqlalchemy-async) for details.

---

## Tests

### Run All Tests

```bash
# Full test suite (no Postgres required — uses aiosqlite)
uv run pytest tests/ -v

# Quiet output
uv run pytest tests/

# Stop on first failure
uv run pytest tests/ -x

# Show local variables on failure
uv run pytest tests/ -v --tb=long
```

### Run by Layer

```bash
# Unit tests only
uv run pytest tests/unit/ -v

# Integration tests only
uv run pytest tests/integration/ -v

# A specific test file
uv run pytest tests/test_observations.py -v

# A specific test by keyword (name match)
uv run pytest tests/ -k "test_create" -v

# A specific test by exact node ID
uv run pytest tests/test_observations.py::test_create_observation -v
```

### Run with Real PostgreSQL

Quick method (using script):

```bash
# Starts container, runs tests, cleans up automatically
./scripts/testing/01-test-with-postgres.sh tests/integration/observations/test_concurrency.py -v
```

#### Manual Method

```bash
# Ensure fixture can auto-provision test DB
unset DATABASE_URL_TEST

# Run tests
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/integration/observations/test_query_analysis.py -v

# Run specific test
uv run pytest tests/integration/observations/test_query_analysis.py::TestQueryAnalysis::test_date_range_query_uses_index -xvs
```

#### Settings

- DATABASE_URL_TEST unset (recommended): pytest fixtures start an ephemeral Postgres via testcontainers
- Optional override: set DATABASE_URL_TEST to an existing PostgreSQL URL

#### Notes

- Default: SQLite in-memory tests only -> 192 passed, 10 skipped (PostgreSQL tests)
- With Docker available for testcontainers -> 202 passed (all tests including EXPLAIN ANALYZE)
- Fixtures use NullPool to avoid cross-loop connection issues

---

## Coverage

```bash
# Run with coverage report in terminal
uv run pytest tests/ --cov=services/ingestor

# Coverage with per-file breakdown
uv run pytest tests/ --cov=services/ingestor --cov-report=term-missing

# Generate HTML report (opens in browser)
uv run pytest tests/ --cov=services/ingestor --cov-report=html
xdg-open htmlcov/index.html  # Ubuntu/Debian

# Fail if below threshold
uv run pytest tests/ --cov=services/ingestor --cov-fail-under=80

# Coverage for a specific module
uv run pytest tests/ --cov=services/ingestor.crud --cov-report=term-missing
```

---

## Code Quality

### Ruff (Linting + Formatting)

```bash
# Check for lint errors
uv run ruff check .

# Check + auto-fix
uv run ruff check . --fix

# Format code
uv run ruff format .

# Check formatting without changing (CI mode)
uv run ruff format . --check

# Lint + format in one command
uv run ruff check . && uv run ruff format .
```

### Pre-commit

```bash
# Install hooks (one-time, per repo)
pre-commit install

# Run all hooks against all files (initial setup / full check)
pre-commit run --all-files

# Run all hooks against staged files only
pre-commit run

# Run a specific hook
pre-commit run ruff --all-files
pre-commit run end-of-file-fixer --all-files

# Skip hooks for a specific commit (use sparingly)
git commit -m "wip" --no-verify

# Update hook versions
pre-commit autoupdate

# Uninstall hooks
pre-commit uninstall
```

> See `docs/pre-commit-setup.md` for hook configuration details.
> Dependabot branch-target troubleshooting checklist: `docs/dev/dependabot-verification-checklist.md`.

---

## API Testing (curl)

### Authentication

#### HTTP Basic Auth (Docs Endpoints)

```bash
# Access protected docs (prompts for username/password)
curl -u admin:admin http://localhost:8000/docs

# Set credentials in .env
# DOCS_USERNAME=admin
# DOCS_PASSWORD=changeme
```

#### Bearer Token (v1 API, Stateless)

```bash
# Static token from .env: API_V1_BEARER_TOKEN=dev-secret-bearer-token
curl -X POST http://localhost:8000/api/v1/observations/batch/protected \
  -H "Authorization: Bearer dev-secret-bearer-token" \
  -H "Content-Type: application/json" \
  -d '[{"source": "curl", "value": 42.0, "metadata": {}}]'
```

#### Session-Based Auth (v1 API, Stateful)

```bash
# 1. Login (creates session, returns Set-Cookie header)
curl -v -X POST "http://localhost:8000/api/v1/observations/auth/login?user_id=alice"

# 2. Extract session_id from Set-Cookie header (curl stores automatically with -b)
curl -b "session_id=<EXTRACTED_SESSION_ID>" \
  -X GET "http://localhost:8000/api/v1/observations/1/secure"
```

### Observations CRUD

```bash
# List all observations (paginated)
curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8000/api/v1/observations?skip=0&limit=10"

# Get single observation
curl -H "X-API-Key: $API_KEY" \
  http://localhost:8000/api/v1/observations/1

# Create an observation
curl -X POST http://localhost:8000/api/v1/observations \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"source": "test", "value": 42.0, "metadata": {}}'

# Batch create
curl -X POST http://localhost:8000/api/v1/observations/batch \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '[{"source":"a","value":1.0},{"source":"b","value":2.0}]'

# Update an observation
curl -X PATCH http://localhost:8000/api/v1/observations/1 \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"value": 99.0}'

# Delete an observation
curl -X DELETE http://localhost:8000/api/v1/observations/1 \
  -H "X-API-Key: $API_KEY"

# Bulk delete
curl -X DELETE http://localhost:8000/api/v1/observations \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"ids": [1, 2, 3]}'
```

### Filter & Search

```bash
# Filter by source
curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8000/api/v1/observations?source=test"

# Filter by value range
curl -H "X-API-Key: $API_KEY" \
  "http://localhost:8000/api/v1/observations?min_value=10&max_value=100"

# Aggregate stats
curl -H "X-API-Key: $API_KEY" \
  http://localhost:8000/api/v1/observations/stats
```

### OpenAPI Docs

```bash
# Interactive Swagger UI
open http://localhost:8000/docs

# Raw OpenAPI JSON
curl http://localhost:8000/openapi.json
```

---

## Docker Compose Profiles

### Development (`docker-compose.dev.yml`)

```bash
# Dev stack: hot-reload, source mount
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# Shell into ingestor container
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec ingestor bash

# View ingestor logs
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs ingestor -f
```

### Production-like (`docker-compose.prod-like.yml`)

```bash
# Prod-like: built image, no source mount
docker compose -f docker-compose.yml -f docker-compose.prod-like.yml up --build

# Check health endpoint in prod-like
curl http://localhost:8000/health
```

### Profiles (selective service start)

```bash
# Start with monitoring stack
docker compose --profile monitoring up -d

# Start vector stack (Qdrant + AI gateway)
docker compose --profile vector up -d

# Start processor worker
docker compose --profile worker up -d

# Start monitoring + vector + worker profiles together
docker compose --profile monitoring --profile vector --profile worker up -d
```

> Available profiles in this repo: `monitoring`, `vector`, `worker`.

---

## Database Operations

### Connect to PostgreSQL

```bash
# Via Docker
docker compose exec db psql -U postgres -d data_pipeline

# Direct psql (if Postgres installed locally)
psql "postgresql://postgres:postgres@localhost:5432/data_pipeline"
```

### Useful psql Commands

```sql
-- List tables
\dt

-- Describe a table
\d observations

-- Show active connections
SELECT pid, usename, application_name, state FROM pg_stat_activity;

-- Show table sizes
SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_statio_user_tables ORDER BY pg_total_relation_size(relid) DESC;

-- Explain a query
EXPLAIN ANALYZE SELECT * FROM observations WHERE source = 'test' LIMIT 10;
```

### Redis

```bash
# Connect to Redis CLI via Docker
docker compose exec redis redis-cli

# Check all keys (dev only)
docker compose exec redis redis-cli KEYS "*"

# Flush all cache (dev only)
docker compose exec redis redis-cli FLUSHALL

# Monitor live commands
docker compose exec redis redis-cli MONITOR
```

---

## Observability

### Prometheus Metrics

```bash
# View raw metrics
curl http://localhost:8000/metrics

# Prometheus UI (if compose profile started)
open http://localhost:9090

# Grafana UI (if compose profile started)
open http://localhost:3000
# Default credentials: admin / admin
```

### Logs

```bash
# Tail ingestor logs (Docker)
docker compose logs ingestor -f

# Filter for errors only
docker compose logs ingestor -f | grep '"level":"ERROR"'

# Filter by correlation ID
docker compose logs ingestor | grep '"cid":"<value>"'
```

---

## Load Testing

### k6

```bash
# Install k6 (Linux)
sudo apt-get install k6

# Run a load test script
k6 run scripts/load_test.js

# With custom VUs and duration
k6 run --vus 50 --duration 30s scripts/load_test.js

# Output results to JSON
k6 run --out json=results.json scripts/load_test.js
```

### Locust (if configured)

```bash
# Start Locust web UI
uv run locust -f scripts/testing/locustfile.py --host http://localhost:8000

# Headless mode
uv run locust -f scripts/testing/locustfile.py \
  --host http://localhost:8000 \
  --users 100 --spawn-rate 10 --run-time 60s --headless
```

---

## Infrastructure & Terraform (Floci)

### One-Time Setup

First, configure AWS sandbox profile (see [docs/setup/sandbox-aws-profile.md](setup/sandbox-aws-profile.md)):

```bash
# Add to ~/.aws/credentials
[sandbox]
aws_access_key_id     = test
aws_secret_access_key = test

# Add to ~/.aws/config
[profile sandbox]
region = eu-central-1
```

### Session Initialization

```bash
# Start Floci emulator
just sandbox-up

# Initialize Terraform backend (once per terminal session before first plan)
just tf-init
```

### Daily Terraform Workflow

```bash
# Then iterate as many times as needed (same terminal, no re-init)
just tf-plan-local          # Review resources to create/modify
just tf-apply-local         # Apply the plan
just tf-plan-local          # Make changes, plan again
just tf-apply-local         # Apply the new plan
# ... repeat as needed
```

**Note:** You only run `tf-init` once when you open a new terminal. Subsequent plan/apply commands in the same terminal don't need re-initialization.

### State Inspection

```bash
# View all deployed resources and their attributes
just tf-show-local

# List all managed resources by ID
just tf-state-list
```

### Full Reset

```bash
# Destroy all resources and start fresh (init → plan → apply)
just tf-apply-local-fresh

# Or manually destroy and keep state backend
just tf-destroy-local
```

### Real AWS (Dev Environment)

```bash
# Plan against real AWS (requires AWS credentials and backend config)
just tf-plan-dev

# Apply real AWS infrastructure
just tf-apply-dev
```

### Cleanup

```bash
# Destroy Floci infrastructure
just tf-destroy-local

# Stop Floci emulator
just sandbox-down
```

---

## Git & Conventional Commits

```bash
# Commit format: <type>(<scope>): <description>
git commit -m "feat(observations): add batch delete endpoint"
git commit -m "fix(auth): handle expired JWT token gracefully"
git commit -m "docs(commands): add load testing section"
git commit -m "refactor(crud): extract pagination helper"
git commit -m "test(observations): add integration test for batch create"
git commit -m "chore(deps): bump SQLAlchemy to 2.0.36"

# Types: feat, fix, docs, style, refactor, test, chore, perf, ci
```

---

## Data Zoo Platform Services (Phases 1–8)

Commands will be added here as each phase is built.

### Phase 1: Kafka/Redpanda (Event Streaming)

```bash
# Start Redpanda
docker compose -f docker-compose.dataZoo.yml up redpanda -d

# Create a topic
docker exec -it redpanda rpk topic create observations-raw --partitions 3

# List topics
docker exec -it redpanda rpk topic list

# Produce test message
docker exec -it redpanda rpk topic produce observations-raw

# Consume from beginning
docker exec -it redpanda rpk topic consume observations-raw --from-beginning
```

### Phase 2: MongoDB (Document Store)

```bash
# Start MongoDB via compose
docker compose -f docker-compose.dataZoo.yml up mongo -d

# Connect to Mongo shell
docker exec -it mongo mongosh

# Switch database
use dataZoo

# List collections
show collections
```

### Phase 3: Qdrant (Vector Store)

```bash
# Start Qdrant
docker compose -f docker-compose.dataZoo.yml up qdrant -d

# Qdrant UI
open http://localhost:6333/dashboard

# Check health
curl http://localhost:6333/healthz
```

### Phase 5: Ollama (Local LLM)

```bash
# Pull a model
ollama pull llama3.2

# Run interactively
ollama run llama3.2

# List models
ollama list

# Check running models
ollama ps
```
