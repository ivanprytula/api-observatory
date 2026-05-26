# Daily Development Workflows

Track: A — Product and Onboarding

> Common commands and workflows for active development.
>
> **Note**: Use bash scripts in `scripts/` for automation. This document explains what each workflow does.

---

## Quick Reference

Use this doc for workflow intent and sequencing.
[dev/commands.md](dev/commands.md) has the complete command catalog; the most common tasks are listed below.

Most workflows are available as executable scripts:

```bash
# Host checks + local troubleshooting folders
just doctor

# Full bootstrap (first time)
bash scripts/setup/01-bootstrap-dev-environment.sh

# Daily service start
bash scripts/daily/01-start-dev-services.sh          # Mode 2: infra only (no ingestor), adds Jaeger
just up                                              # Mode 1 (preferred): full stack — db, redis, redpanda, ingestor, mongodb
just sandbox-up                                      # Optional: Floci local AWS — only if touching S3/SQS/DynamoDB

# End of day
just down                                            # Stop and remove all containers

# Optional runtime profiles
bash scripts/ops/02-compose-profile.sh dev up -d     # Dev resource profile (override file)
bash scripts/ops/02-compose-profile.sh prod-like up -d  # Prod-like resource profile
docker compose --profile monitoring up -d            # Optional monitoring stack
docker compose --profile vector up -d                # Optional vector stack (qdrant + inference)
docker compose --profile worker up -d                # Optional processor worker

# Daily validation
bash scripts/daily/03-run-tests.sh all         # Run all tests
bash scripts/daily/03-run-tests.sh unit        # Run unit tests only
bash scripts/daily/03-run-tests.sh integration # Run integration tests only
uv run alembic upgrade head                   # Apply migrations
uv run alembic downgrade -1                   # Rollback migration
bash scripts/daily/04-quality-checks.sh   # Lint, format, type-check
bash scripts/setup/03-bootstrap-k3d.sh        # Bootstrap local k3d cluster
```

## Validate PR checks (manual merge via GitHub UI)

Use the GitHub web UI to review required checks and perform merges. Alternatively you can inspect
check-run status with the `gh` CLI:

```bash
gh pr checks <pr-number-or-branch>                         # Show checks for the PR
gh pr checks <pr-number-or-branch> --watch --interval 10  # Watch checks until completion
```

## Practical Cadence

Use this cadence to keep fast feedback on every commit while running heavy security scans less often.

```text
Push/PR update (main, develop, feature/*)
  |
  +--> CI
       01 Quality
       02 Unit
       03 Migrations
       04 Integration
       05 E2E
       06 Dependency Audit (PR only)
       07 Docker Build (push/manual only after all checks pass)

Nightly / Weekly
  |
  +--> Security Full Scan (Scheduled and Manual)
  +--> Scheduled CodeQL / CodeQL Analyze

Manual dispatch
  |
  +--> CI
      01 Quality -> 02 Unit -> 03 Migrations -> 04 Integration -> 05 E2E -> 07 Docker Build
  +--> Manual Docker Build (standalone validation)
  +--> Security Full Scan (Scheduled and Manual)
    +--> Scheduled CodeQL / CodeQL Analyze
  +--> Release Promote / CD Deploy
```

Policy summary:

- Run one queued CI workflow on every push and PR update
- Run migrations before integration/e2e so schema failures stop the pipeline early
- Run dependency audit inside the main PR CI chain instead of as a separate workflow
- Run the full security scan on schedule and manual dispatch for broad security coverage
- Run scheduled/manual CodeQL from the separate lightweight security workflow
- Run Docker build only after prior CI checks pass, with standalone manual Docker build kept for ad hoc validation

---

## Workflow 1: Start Development Environment

### What It Does

> **Mode 1 (preferred — Docker-first):** Use `just up` to start the full stack including the ingestor
> container. This is the standard daily workflow.
>
> **Mode 2 (infra-only, uvicorn in terminal):** The script below starts infra services only
> (PostgreSQL, Redis, Redpanda, MongoDB, Jaeger) **without** the ingestor container. Use this
> when you want to run uvicorn directly outside Docker (e.g. for IDE debugging).
> Then run `uv run uvicorn services/ingestor/main:app --reload` in a second terminal.

Starts infra services (Mode 2) in the background:

### Command

```bash
bash scripts/daily/01-start-dev-services.sh
```

### Expected Output

```text
✓ PostgreSQL ready (localhost:5432)
✓ Redis ready (localhost:6379)
✓ Services are healthy
```

### What's Running

After this script (Mode 2 — infra only):

- PostgreSQL (main) is accepting connections on port 5432
- PostgreSQL for DB-dependent tests is auto-provisioned by testcontainers when needed
- Redis is running on port 6379
- Redpanda (Kafka-compatible) is running on port 9092
- MongoDB is running on port 27017
- Jaeger is running on port 16686

**The ingestor API is NOT started by this script.** Start it with `uv run uvicorn services/ingestor/main:app --reload` in a second terminal, or switch to Mode 1 (`just up`) for the full Docker stack.

**Services stay running in the background** until you stop them:

```bash
docker compose stop     # Stop but keep containers
docker compose down     # Stop and remove containers
```

---

## Workflow 2: Run Tests

### Full Test Suite

Runs unit tests (in-memory SQLite) first, then integration tests (PostgreSQL):

```bash
bash scripts/daily/03-run-tests.sh all
```

Expected: ~100+ tests passing

### Unit Tests Only (Fast)

In-memory SQLite, no external services needed:

```bash
bash scripts/daily/03-run-tests.sh unit
```

Expected: ~50 tests, <5 seconds

### Integration Tests Only (PostgreSQL)

Requires dev environment running (`bash scripts/daily/01-start-dev-services.sh`):

```bash
bash scripts/daily/03-run-tests.sh integration
```

Expected: ~50 tests, 10–30 seconds

### Single Test File

```bash
uv run pytest tests/unit/crud/test_records.py -v
```

### Single Test by Name

```bash
uv run pytest tests/ -k test_create_record -v
```

### With Coverage Report

```bash
uv run pytest tests/unit/ --cov=services/ingestor --cov-report=html
xdg-open htmlcov/index.html  # View coverage report
```

---

## Workflow 3: Database Migrations

### Show Current Schema Version

```bash
uv run alembic current
```

Returns the current migration head applied to the database.

### Apply All Pending Migrations

```bash
uv run alembic upgrade head
```

Applies all new migrations from `alembic/versions/` to the database.

### Rollback One Step

```bash
uv run alembic downgrade -1
```

Reverts the most recent migration.

### Create New Migration from Model Changes

After modifying `services/ingestor/models.py`:

```bash
uv run alembic revision --autogenerate -m "add_user_status_field"
```

This generates a new migration file in `alembic/versions/` based on model diffs.

### Dry Run (Show SQL Without Applying)

```bash
uv run alembic upgrade head --sql
```

Shows SQL that would be executed.

### Reset Database (Wipe All Data)

```bash
docker compose exec db psql -U postgres -c "DROP DATABASE data_pipeline;"
uv run alembic upgrade head
```

---

## Workflow 4: Code Quality

### Format & Lint

```bash
bash scripts/daily/04-quality-checks.sh
```

This runs:

- **Ruff format**: Auto-format code to PEP 8 style
- **Ruff lint**: Check for code errors and style issues
- **Type check**: Verify type hints with `pyright`

Expected output: "All checks passed ✓"

### Manual Commands

```bash
# Format code
uv run ruff format services/ingestor/ tests/

# Check for lint issues
uv run ruff check services/ingestor/ tests/

# Type check
uv run pyright services/ingestor/
```

---

## Workflow 5: Override — Run Dev Server Outside Docker

> **Prerequisite**: Stop the ingestor container first to free port 8000:
>
> ```bash
> docker compose stop ingestor
> ```
>
> For the standard Docker-first workflow, the ingestor is already running via `just up` —
> you do not need this workflow for normal development.

### With Auto-Reload

```bash
uv run uvicorn services/ingestor/main:app --reload
```

Server starts at `http://localhost:8000`

**Features**:

- Auto-reloads when you save Python files
- Shows detailed error messages
- Hot-reload for dependency injection changes

### Access API Documentation

Once server is running:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

---

## Workflow 6: Auth and RBAC Smoke Checks

Use these quick checks after touching auth, middleware, or route dependencies.

### Session Login with Explicit Role

```bash
curl -i -X POST "http://localhost:8000/api/v1/records/auth/login?user_id=alice&role=writer"
```

Expected: `Set-Cookie: session_id=...` in response headers.

### Writer Route (Should Succeed for writer/admin)

```bash
curl -i -X PATCH "http://localhost:8000/api/v1/records/1/secure/archive" \
  --cookie "session_id=<SESSION_ID>"
```

Expected: `200 OK` for `writer`/`admin`, `403` for `viewer`.

### Admin Route (Should Fail for writer)

```bash
curl -i -X DELETE "http://localhost:8000/api/v1/records/1/secure/delete" \
  --cookie "session_id=<SESSION_ID>"
```

Expected: `403` unless session role is `admin`.

### JWT Write Route (v2)

```bash
TOKEN=$(curl -s -X POST "http://localhost:8000/api/v2/records/auth/token" | jq -r '.access_token')

curl -i -X POST "http://localhost:8000/api/v2/records/jwt" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"source":"rbac-check","timestamp":"2026-01-01T00:00:00","data":{"ok":true},"tags":["smoke"]}'
```

Expected: `201` with writer/admin token; `403` when token roles are insufficient.

### Health Check

```bash
curl http://localhost:8000/health
```

Should return: `{"status":"healthy"}`

---

## Workflow 7: Manage GitHub Actions Config (Daily Ops)

Use `scripts/ops/01-gh-actions-config.sh` for day-to-day CI/CD configuration updates.

### Common Tasks

```bash
repo="ivanprytula/api-observatory"

# Rotate/update environment variable values
scripts/ops/01-gh-actions-config.sh vars set ECS_SERVICE_NAME ingestor --env dev --repo "$repo"
scripts/ops/01-gh-actions-config.sh vars set ECS_SERVICE_NAME_AI_GATEWAY inference --env dev --repo "$repo"
scripts/ops/01-gh-actions-config.sh vars set ECS_TASK_DEFINITION_FAMILY_AI_GATEWAY inference --env dev --repo "$repo"

# Update signer identity policy used by CD verification
scripts/ops/01-gh-actions-config.sh vars set COSIGN_CERTIFICATE_IDENTITY \
  "https://github.com/${repo}/.github/workflows/docker-build-reusable.yml@refs/heads/main" \
  --env prod --repo "$repo"

# Rotate secret value
scripts/ops/01-gh-actions-config.sh secrets set SENTRY_AUTH_TOKEN "$SENTRY_AUTH_TOKEN" --env prod --repo "$repo"

# Inspect current settings
scripts/ops/01-gh-actions-config.sh vars list --env prod --repo "$repo"
scripts/ops/01-gh-actions-config.sh secrets list --env prod --repo "$repo"
```

### OIDC Template Operations

```bash
repo="ivanprytula/api-observatory"

# View current OIDC subject template
scripts/ops/01-gh-actions-config.sh oidc get --repo "$repo"

# Set custom claims list
scripts/ops/01-gh-actions-config.sh oidc set --claims repo,context,job_workflow_ref --repo "$repo"

# Reset to GitHub default subject template
scripts/ops/01-gh-actions-config.sh oidc reset --repo "$repo"
```

### Safety Notes

- Prefer environment-scoped updates (`--env`) for deploy-related values.
- Update production values via protected branches and approved change windows.
- Keep all script usage in terminal history for auditability.

---

## Workflow 8: Test API Endpoints

> **Tip:** The curl examples below are for quick smoke tests and scripting. For interactive
> exploration, use the Swagger UI at `http://localhost:8000/docs` or your preferred HTTP client
> (Bruno, Postman, httpie, VS Code REST Client).

### Dashboard Admin UI (Pillar 7)

Use the new dashboard control surface for operator workflows:

- Open `http://localhost:8003/admin` for Admin Workflows.
- Refresh worker health from the Worker Health panel.
- Lookup one task ID from the Task Lookup panel.
- Trigger one-record reruns from Manual Rerun.
- Create role-aware test sessions from Session Bootstrap (RBAC).

These UI actions call existing ingestor APIs and are useful for fast operational checks without crafting manual curl commands.

### Manual HTTP Requests

```bash
# Create a record
curl -X POST http://localhost:8000/api/v1/records \
  -H "Content-Type: application/json" \
  -d '{"source": "cli", "timestamp": "2024-04-22T12:00:00", "data": {}}'

# Fetch records
curl -X GET http://localhost:8000/api/v1/records

# With pagination
curl -X GET 'http://localhost:8000/api/v1/records?limit=10&offset=0'
```

### Using HTTP Client Script

```bash
python scripts/tools/http-clients-demo.py
```

This script demonstrates various API calls (create, read, update, delete).

---

## Workflow 9: Background Worker Testing

### Submit Batch Ingestion Job

```bash
curl -X POST http://localhost:8000/api/v1/background/ingest/batch \
  -H "Content-Type: application/json" \
  -d '[
    {"source": "batch1", "timestamp": "2024-04-22T12:00:00", "data": {"value": 100}},
    {"source": "batch1", "timestamp": "2024-04-22T12:00:01", "data": {"value": 200}}
  ]'
```

Returns: `{"task_id": "uuid-here", "status": "queued", ...}`

### Poll Task Status

```bash
curl -X GET http://localhost:8000/api/v1/background/tasks/UUID-HERE
```

Returns: `{"task_id": "...", "status": "running|succeeded|failed", ...}`

### Check Worker Health

```bash
curl -X GET http://localhost:8000/api/v1/background/workers/health
```

Returns: Queue depth, active workers, submitted/processed counters

---

## Workflow 10: Metrics & Observability

### Prometheus Metrics

```bash
# Raw metrics endpoint
curl http://localhost:9000/metrics

# Or visit dashboard:
xdg-open http://localhost:9090
```

### Available Metrics

- `http_requests_total` — All HTTP requests by method/endpoint/status
- `http_request_duration_seconds` — Response time histogram
- `pipeline_records_ingested_total` — Records processed
- `pipeline_job_executions_total` — Scheduled job runs
- `background_jobs_submitted_total` — Batch jobs submitted

### Distributed Tracing (Jaeger)

```bash
# View traces and spans
xdg-open http://localhost:16686
```

Traces show:

- Request flow through middleware → router → CRUD
- Database query timing
- External HTTP calls (if traced)

---

## Workflow 11: Database Inspection

### Connect via psql

```bash
docker compose exec db psql -U postgres -d data_pipeline
```

Then:

```sql
-- List tables
\dt

-- Show schema of records table
\d records

-- Query records
SELECT id, source, created_at FROM records LIMIT 10;

-- Check migrations applied
SELECT version, description, installed_on FROM alembic_version;
```

### Export Data

```bash
# Backup to SQL file
docker compose exec db pg_dump -U postgres data_pipeline > backup.sql

# Restore from backup
docker compose exec db psql -U postgres data_pipeline < backup.sql
```

---

## Workflow 12: Load Testing

### Run Load Test

```bash
bash scripts/testing/03-load-test.sh
```

This script runs k6 load tests with:

- 10 virtual users
- Ramp-up over 30 seconds
- 5-minute test duration
- Checks for errors and performance thresholds

### Locust Web UI

Alternative load testing tool with web dashboard:

```bash
# Start Locust
uv run locust -f scripts/testing/locustfile.py --host=http://localhost:8000

# Visit: http://localhost:8089
```

---

## Common Issues & Solutions

### "Connection refused: PostgreSQL"

```bash
# Check if services are running
docker compose ps

# If not running, start them
bash scripts/daily/01-start-dev-services.sh

# If stuck, restart
docker compose restart db
```

### "Port already in use"

```bash
# Find process using port
lsof -i :5432  # PostgreSQL

# Kill process or edit docker-compose.yml to use different port
```

### "Test database locked"

```bash
# Restart test PostgreSQL
docker compose restart db_test

# Or drop test database and recreate
docker compose exec db_test psql -U postgres -c "DROP DATABASE test_database;"
```

### "Module not found" After Git Pull

```bash
# Dependencies may have changed
uv sync

# Then re-run tests
bash scripts/daily/03-run-tests.sh unit
```

---

## Workflow 13: Ship a Feature

Full journey from feature branch to production. Derived from `ci.yml`, `cd-deploy.yml`, and
`release-promote.yml`.

### 1. Branch from develop

```bash
git checkout develop && git pull
git checkout -b feature/my-feature
```

### 2. Develop, commit, push

Pre-commit hooks run on every `git commit`. To run manually:

```bash
bash scripts/daily/04-quality-checks.sh
uv run pytest tests/unit/ -q
git push -u origin feature/my-feature
```

CI runs quality + unit tests on every push.

### 3. Open PR → develop

Opening a PR triggers the full check suite:

| Step | What runs |
|------|-----------|
| Quality | ruff, pyright, pre-commit |
| Unit | in-memory SQLite |
| Migrations | alembic check against test DB |
| Integration | PostgreSQL, Redis |
| E2E | full stack |
| Dependency Audit | pip-audit / safety |

Watch live:

```bash
gh pr checks <pr-number> --watch --interval 10
```

All checks must pass. Merge via GitHub UI (or `gh pr merge`).

### 4. Merge → develop, Docker build

CI re-runs on merge. On success, `07 Docker Build` pushes a tagged image to ECR.
Note the image tag (`sha-xxxxxxx`) from the Actions run.

### 5. Deploy to dev

Manual trigger via **Actions → CD Deploy → Run workflow**, or:

```bash
gh workflow run cd-deploy.yml \
  -f environment=dev \
  -f service=ingestor \
  -f image-uri=sha-XXXXXXX
```

### 6. Promote to prod

Once dev is validated, promote the same image digest — no rebuild:

```bash
# Step 1: re-tag the image
gh workflow run release-promote.yml \
  -f service=ingestor \
  -f source-ref=sha-XXXXXXX \
  -f target-tag=prod \
  -f environment=prod

# Step 2: deploy the promoted tag
gh workflow run cd-deploy.yml \
  -f environment=prod \
  -f service=ingestor \
  -f image-uri=sha-XXXXXXX
```

> **Note**: `dev` is the active deployment environment for this portfolio project.
> The dev → stage → prod pattern above is shown for full-scale team workflow illustration.
> Staging is on the future roadmap. Both `dev` and `prod` dispatches are manual —
> a human approves every production change.

---

## Next Steps

- **Explore the architecture**: [04 — Architecture Overview](04-architecture-overview.md)
- **Use test/quality commands reference**: [Dev Commands](dev/commands.md)
- **Review design decisions**: [Design Decisions](design/decisions.md)
