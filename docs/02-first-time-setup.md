# First-Time Project Setup

Track: A — Product and Onboarding

> Clone, install dependencies, then start the full stack — core services **and** Floci (local AWS simulator) — before touching any real cloud credentials.
>
> **Time**: 10–15 minutes (mostly waiting for Docker to pull images).

---

## Step 1: Clone & Navigate to Project

```bash
git clone https://github.com/ivanprytula/api-observatory.git
cd api-observatory
```

---

## Step 2: Run Automated Setup

The entire setup is automated in a single bash script:

```bash
just doctor  # read-only checks — safe to re-run at any time, even before uv sync
bash scripts/setup/01-bootstrap-dev-environment.sh
```

This script will:

- ✅ Install `uv` if missing
- ✅ Copy `.env.example` to `.env` (use defaults or customize)
- ✅ Sync Python dependencies (`uv sync`)
- ✅ Start PostgreSQL and Redis
- ✅ Wait for services to be healthy
- ✅ Apply database migrations (`alembic upgrade head`)

**Expected output:**

```sh
✓ uv already installed (v...)
✓ .env created with defaults
✓ Dependencies synced
✓ Services healthy
✓ Database schema initialized
✓ Development environment ready!

Next steps:
1. Open API docs in browser: http://localhost:8000/docs
2. Open API docs via nginx (if certs configured): https://localhost/api/docs
```

**Pre-commit setup** (run once after clone to prevent commit errors):

```bash
pre-commit install  # Install Git hooks (prevents bad commits)
```

You may also want to run manually before your first commit:

```bash
uv run pre-commit run --all-files  # The repo is clean at clone — this should pass
```

After the first commit, pre-commit hooks will run automatically on every commit.

---

## Step 3: Start the Core Stack

Start the core services — database, cache, message broker, and API. The nginx service is optional and provides HTTPS parity with production.

```bash
just up      # db, redis, redpanda, ingestor (HTTP on :8000)
# For HTTPS parity (requires certs — run Step 6 first):
just up-https  # includes nginx on :443
just migrate # apply Alembic migrations (safe to re-run)
```

`just up` covers all feature development workflows. The Floci AWS simulator is a separate pre-deploy playground — you do not need it for day-to-day coding. See [docs/floci-aws-deployment-workflow.md](floci-aws-deployment-workflow.md) when you are ready to rehearse AWS-integrated flows before a real cloud deployment.

For a description of every service and its port, see [What Just Happened](#what-just-happened) below.

For a complete list of environment variables and guidance on storing secrets (JWT keys, OpenAI key, AWS credentials, etc.) see: [setup/environment-setup.md](../setup/environment-setup.md)

---

## Step 4: Verify Setup

```bash
# Check all containers are running
docker compose ps

# Verify the ingestor API is responding (started inside Docker by `just up`)
curl http://localhost:8000/health
# Should return: {"status":"healthy"}

# Also available via nginx (after just up with certs): https://localhost/api/docs

# Run quick test
uv run pytest tests/unit/ -q
# Should show: 192 passed, 10 skipped
```

> **Mode 2 (optional — IDE debugging/hot-reload):** Stop the ingestor container first, then run uvicorn locally:
>
> ```bash
> docker compose stop ingestor
> uv run uvicorn services.ingestor.main:app --reload
> ```
>
> See [dev/commands.md](dev/commands.md#run-dev-server-no-docker) for details.

---

## Step 5 (Optional): Customize Environment

The setup creates a `.env` file with defaults. Edit it if needed:

```bash
# View current configuration
cat .env

# Edit if needed (most defaults are fine for local dev)
nano .env

# Restart Docker Compose services after changing non-app config (e.g. Redis URL, DB port)
docker compose restart
# Note: if you changed DATABASE_URL and are running uvicorn directly (not in Docker),
# stop uvicorn (Ctrl+C) and restart it — docker compose restart does not affect it.
```

For the full env var matrix (all variables, defaults, CI/CD and deployment contexts), see
[Environment Setup](setup/environment-setup.md).

---

## Step 6 (Optional): Enable HTTPS for Local Parity

For maximum local → dev/prod parity, enable HTTPS via nginx. This is optional since HTTP on `:8000` works for development.

```bash
# Install mkcert (one-time system install)
# macOS:    brew install mkcert
# Ubuntu:   sudo apt install mkcert

# Generate trusted local certificates
bash scripts/setup/02-setup-local-https.sh

# Start stack with nginx (HTTPS on :443)
just up-https

# Verify HTTPS is working
curl -v https://localhost/health
curl -k https://localhost/api/docs   # -k only needed if first run before cert trust propagates
```

**Expected output after `just up-https`:**

```text
✓ All services running (db, redis, redpanda, ingestor, nginx)
✓ HTTPS available at https://localhost + https://localhost/api/*
```

After this step, access the application via HTTPS:

| URL | Purpose |
| --- | --- |
| `https://localhost/` | Dashboard (when frontend built) |
| `https://localhost/api/docs` | Swagger UI (interactive API docs) |
| `https://localhost/api/redoc` | ReDoc (alternative API docs) |
| `https://localhost/prometheus/` | Prometheus metrics |
| `https://localhost/jaeger/` | Jaeger tracing |

---

## Step 7 (When Ready): CI/CD and Real AWS Access

> Come back here once the project is running locally via Floci (Steps 3–4).
> This step requires an AWS account, OIDC trust configuration, and GitHub repository secrets.
> For the full progression path — local Floci → AWS staging → production — see
> [Floci + AWS Deployment Workflow](floci-aws-deployment-workflow.md).

Use `scripts/ops/01-gh-actions-config.sh` to set repository/environment variables, secrets, and OIDC subject template from the command line.

Prerequisites:

- `gh auth login` has been completed
- You have admin/maintainer access to the repository
- `gh` and `jq` are installed

Common bootstrap commands:

```bash
repo="ivanprytula/api-observatory"

# Repository-wide defaults
scripts/ops/01-gh-actions-config.sh vars set AWS_REGION eu-central-1 --repo "$repo"
scripts/ops/01-gh-actions-config.sh vars set COSIGN_CERTIFICATE_IDENTITY \
  "https://github.com/${repo}/.github/workflows/docker-build-reusable.yml@refs/heads/main" \
  --repo "$repo"

# Environment-scoped values
scripts/ops/01-gh-actions-config.sh vars set ECS_CLUSTER_NAME data-zoo-dev --env dev --repo "$repo"   # existing AWS ECS cluster name
scripts/ops/01-gh-actions-config.sh vars set ECS_CLUSTER_NAME data-zoo-prod --env prod --repo "$repo" # existing AWS ECS cluster name

# Per-service ECS deploy targets (repeat for each environment you use)
scripts/ops/01-gh-actions-config.sh vars set ECS_SERVICE_NAME ingestor --env dev --repo "$repo"
scripts/ops/01-gh-actions-config.sh vars set ECS_TASK_DEFINITION_FAMILY ingestor --env dev --repo "$repo"
scripts/ops/01-gh-actions-config.sh vars set ECS_SERVICE_NAME_AI_GATEWAY inference --env dev --repo "$repo"
scripts/ops/01-gh-actions-config.sh vars set ECS_TASK_DEFINITION_FAMILY_AI_GATEWAY inference --env dev --repo "$repo"
scripts/ops/01-gh-actions-config.sh vars set ECS_SERVICE_NAME_QUERY_API analytics --env dev --repo "$repo"
scripts/ops/01-gh-actions-config.sh vars set ECS_TASK_DEFINITION_FAMILY_QUERY_API analytics --env dev --repo "$repo"
scripts/ops/01-gh-actions-config.sh vars set ECS_SERVICE_NAME_PROCESSOR processor --env dev --repo "$repo"
scripts/ops/01-gh-actions-config.sh vars set ECS_TASK_DEFINITION_FAMILY_PROCESSOR processor --env dev --repo "$repo"
scripts/ops/01-gh-actions-config.sh vars set ECS_SERVICE_NAME_DASHBOARD dashboard --env dev --repo "$repo"
scripts/ops/01-gh-actions-config.sh vars set ECS_TASK_DEFINITION_FAMILY_DASHBOARD dashboard --env dev --repo "$repo"

# Example secret
scripts/ops/01-gh-actions-config.sh secrets set AWS_ACCOUNT_ID "123456789012" --repo "$repo"

# Optional OIDC customization for subject template
scripts/ops/01-gh-actions-config.sh oidc set --claims repo,context,job_workflow_ref --repo "$repo"
```

Quick verification:

```bash
scripts/ops/01-gh-actions-config.sh vars list --repo "$repo"
scripts/ops/01-gh-actions-config.sh vars list --env dev --repo "$repo"
scripts/ops/01-gh-actions-config.sh oidc get --repo "$repo"
```

---

## What Just Happened?

### Services Started

**`just up` starts (core MVP stack):**

```text
PostgreSQL 17          localhost:5432   → Primary persistence (scorecards, observations, drift events)
Redis                  localhost:6379   → Scorecard TTL cache, WebSocket pub/sub, rate-limit backend
Redpanda (Kafka)       localhost:9092   → Drift events, async processing, DLQ
Ingestor API           localhost:8000   → FastAPI — probes, scorecards, agent enrichment
```

**`just up-https` adds HTTPS parity:**

```text
nginx (HTTPS proxy)      localhost:443    → reverse proxy with SSL termination, rate limiting
                       localhost:80     → HTTP → HTTPS redirect
```

**Additional services (optional):**

```text
Floci (AWS emulator)   localhost:4566   → pre-deploy sandbox only: just sandbox-up
PostgreSQL (tests)     auto-provisioned → ephemeral DB via testcontainers
```

### Database Schema Created

Alembic migrations were applied, creating tables:

- `observations` — ingested data observations
- `pipeline_jobs` — job execution history
- And others based on current phase

### Dependencies Installed

Python dependencies are installed in `.venv/`:

- FastAPI, Pydantic v2, SQLAlchemy 2.0
- APScheduler, pytest, Prometheus client, OpenTelemetry
- And many more (see `pyproject.toml`)

---

## Common Next Steps

For canonical command workflows, use **[03 — Daily Development](03-daily-development.md)** and **[Dev Commands](dev/commands.md)**.

### Access the Application

| URL | Purpose |
| --- | --- |
| `http://localhost:8000/` | API (direct HTTP, always available) |
| `http://localhost:8000/docs` | Swagger UI (direct HTTP) |
| `https://localhost/` | Dashboard (requires `just up-https`) |
| `https://localhost/api/docs` | Swagger UI via nginx (HTTPS) |
| `https://localhost/api/redoc` | ReDoc via nginx (HTTPS) |
| `https://localhost/prometheus/` | Prometheus via nginx (HTTPS) |
| `https://localhost/jaeger/` | Jaeger via nginx (HTTPS) |

### Submit a Test Request

```bash
# Direct HTTP (always works after `just up`):
curl -X POST http://localhost:8000/api/v1/observations \
  -H "Content-Type: application/json" \
  -d '{"source": "test", "timestamp": "2024-04-22T12:00:00", "data": {}}'

# Via nginx HTTPS (requires `just up-https` + certificates):
curl -X POST https://localhost/api/v1/observations \
  -H "Content-Type: application/json" \
  -d '{"source": "test", "timestamp": "2024-04-22T12:00:00", "data": {}}' \
  -k  # -k only needed on first run before cert trust propagates
```

For additional API usage and request patterns, use Swagger at `http://localhost:8000/docs` (direct) or `https://localhost/api/docs` (HTTPS via nginx).
For ongoing command workflows, use [03-daily-development.md](03-daily-development.md) and
[dev/commands.md](dev/commands.md).

---

## Stopping Services

```bash
# Stop without removing (data persists)
docker compose stop

# Stop and remove containers (data persists in named volumes)
docker compose down

# Stop, remove containers, AND delete data
docker compose down -v
```

---

## Troubleshooting

### Services Won't Start

```bash
# Check Docker is running
docker ps

# Check for port conflicts
lsof -i :5432      # PostgreSQL
lsof -i :6379      # Redis
lsof -i :443       # nginx

# If ports in use, either:
# 1. Stop the other service using that port
# 2. Edit docker-compose.yml to use different ports
```

### Migrations Failed

```bash
# Check migration status
uv run alembic current

# View migration history
uv run alembic history --verbose

# Reapply from scratch
docker compose exec db psql -U postgres -c "DROP DATABASE data_pipeline;"
uv run alembic upgrade head
```

### Certificate Trust Issues

```bash
# Reinstall certificates (Ubuntu/Debian)
bash scripts/setup/02-setup-local-https.sh

# Or manually:
mkcert -install
```

### Python Dependencies Conflict

```bash
# Clean and reinstall
rm -rf .venv
uv sync --upgrade
```

---

## Next Steps

1. **Configure environment variables**: See **[Environment Setup](setup/environment-setup.md)**
2. **Understand daily workflows**: See **[03 — Daily Development](03-daily-development.md)**
3. **Explore the architecture**: See **[04 — Architecture Overview](04-architecture-overview.md)**
4. **Enable HTTPS for production parity**: `bash scripts/setup/02-setup-local-https.sh` then `just up-https`
5. **Run full test suite**: `bash scripts/daily/03-run-tests.sh all`
6. **Start the dev server**: `uv run uvicorn ingestor.main:app --reload`

---

## Important: Environment for Testing

Most unit tests use **in-memory SQLite** and don't require a running PostgreSQL. Integration tests do require PostgreSQL.

To run tests:

```bash
# Run all (unit + integration)
uv run pytest tests/ -v

# Just unit tests (fast, no DB required)
uv run pytest tests/unit/ -v

# Just integration tests (requires PostgreSQL)
uv run pytest tests/integration/ -v
```

See **[Dev Commands](dev/commands.md)** for detailed testing and CI-related command workflows.
