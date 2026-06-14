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

Use `just` recipes instead of a monolithic bootstrap script:

```bash
just doctor                  # read-only checks — safe to re-run at any time
cp .env.example .env        # create local configuration
uv sync                     # sync Python dependencies
just up                     # start Docker services (db, cache, broker, ingestor, dashboard)
just migrate                # apply database migrations
```

**Expected output:**

```sh
✓ Services healthy
✓ Database schema initialized
```

Next steps:

1. Open API docs with the active local URL helper: `bash scripts/daily/local-url.sh open /api/docs`
2. Switch to HTTPS parity with `LOCAL_API_SCHEME=https just up-https` when needed

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

Start the core services — database, cache, message broker, API, and dashboard. The edge service is optional and provides HTTPS parity with production.

```bash
just up      # db, cache, broker, ingestor, dashboard (direct HTTP API)
# For HTTPS parity (requires certs — see Step 6):
LOCAL_API_SCHEME=https just up-https  # includes edge on :443
just migrate # apply Alembic migrations (safe to re-run)
```

`just up` covers all feature development workflows. The Floci AWS simulator is a separate pre-deploy playground — you do not need it for day-to-day coding. See [floci-aws-deployment-workflow.md](../floci-aws-deployment-workflow.md) when you are ready to rehearse AWS-integrated flows before a real cloud deployment.

For a description of every service and its port, see [What Just Happened](#what-just-happened) below.

For a complete list of environment variables and guidance on storing secrets (JWT keys, OpenAI key, AWS credentials, etc.) see: [setup/environment-setup.md](../setup/environment-setup.md)

---

## Step 4: Verify Setup

```bash
# Check all containers are running
docker compose ps

# Verify the ingestor API is responding (started inside Docker by `just up`)
source scripts/daily/local-url.sh
curl_local -sf "$(local_api_url /health)"
# Should return: {"status":"healthy"}

# API docs follow the active local URL mode
bash scripts/daily/local-url.sh open /api/docs

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

See [setup/environment-setup.md](../setup/environment-setup.md) for detailed environment variable configuration, defaults, and CI/CD contexts.

---

## Step 6 (Optional): Enable HTTPS for Local Parity

See [setup/local-https-setup.md](../setup/local-https-setup.md) for mkcert installation, local CA setup, certificate generation, and edge HTTPS configuration.

---

## Step 7 (When Ready): CI/CD and Real AWS Access

> Come back here once the project is running locally via Floci (Steps 3–4).
> This step requires an AWS account, OIDC trust configuration, and GitHub repository secrets.
> For the full progression path — local Floci → AWS staging → production — see
> [Floci + AWS Deployment Workflow](floci-aws-deployment-workflow.md).

Use `gh` directly — it natively supports vars, secrets, and environment-scoped configuration:

```bash
repo="ivanprytula/api-observatory"

# Repository-wide variables
gh variable set AWS_REGION --body "eu-central-1" --repo "$repo"
gh variable set COSIGN_CERTIFICATE_IDENTITY \
  --body "https://github.com/${repo}/.github/workflows/docker-build-reusable.yml@refs/heads/main" \
  --repo "$repo"

# Environment-scoped variables
gh variable set ECS_CLUSTER_NAME --env dev --body "data-zoo-dev" --repo "$repo"
gh variable set ECS_CLUSTER_NAME --env prod --body "data-zoo-prod" --repo "$repo"

# Per-service ECS targets
gh variable set ECS_SERVICE_NAME --env dev --body "ingestor" --repo "$repo"
gh variable set ECS_TASK_DEFINITION_FAMILY --env dev --body "ingestor" --repo "$repo"
gh variable set ECS_SERVICE_NAME_AI_GATEWAY --env dev --body "inference" --repo "$repo"
gh variable set ECS_TASK_DEFINITION_FAMILY_AI_GATEWAY --env dev --body "inference" --repo "$repo"
gh variable set ECS_SERVICE_NAME_QUERY_API --env dev --body "analytics" --repo "$repo"
gh variable set ECS_TASK_DEFINITION_FAMILY_QUERY_API --env dev --body "analytics" --repo "$repo"
gh variable set ECS_SERVICE_NAME_PROCESSOR --env dev --body "processor" --repo "$repo"
gh variable set ECS_TASK_DEFINITION_FAMILY_PROCESSOR --env dev --body "processor" --repo "$repo"
gh variable set ECS_SERVICE_NAME_DASHBOARD --env dev --body "dashboard" --repo "$repo"
gh variable set ECS_TASK_DEFINITION_FAMILY_DASHBOARD --env dev --body "dashboard" --repo "$repo"

# Secrets (value read from matching local env var)
gh secret set AWS_ACCOUNT_ID --body "123456789012" --repo "$repo"

# OIDC customization
gh api --method PUT \
  -H "Accept: application/vnd.github+json" \
  "/repos/${repo}/actions/oidc/customization/sub" \
  -f use_default=false \
  -f "include_claim_keys[]=repo" \
  -f "include_claim_keys[]=context"
```

Quick verification:

```bash
gh variable list --repo "$repo"
gh variable list --env dev --repo "$repo"
gh api "/repos/${repo}/actions/oidc/customization/sub" --jq '.include_claim_keys'
```

---

## What Just Happened?

### Services Started

**`just up` starts (core MVP stack):**

```text
PostgreSQL 17          127.0.0.1:5432   → Primary persistence (scorecards, observations, drift events)
Cache                  127.0.0.1:6379   → Scorecard TTL cache, WebSocket pub/sub, rate-limit backend
Redpanda (Kafka)       127.0.0.1:9092   → Drift events, async processing, DLQ
Ingestor API           127.0.0.1:8000   → FastAPI — probes, scorecards, agent enrichment
Dashboard (Streamlit)  127.0.0.1:8501   → Visual UI for scorecards, drift, live stream
```

**Optional services:**

```text
Floci (AWS emulator)   127.0.0.1:4566   → pre-deploy sandbox only: just floci-up
```

**Additional services (optional):**

```text
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

Use the shared local URL helper so HTTP and HTTPS modes stay in sync:

```bash
bash scripts/daily/local-url.sh open /api/docs
LOCAL_API_SCHEME=https bash scripts/daily/local-url.sh open /api/docs
```

Full URL matrix: [setup/local-url-matrix.md](setup/local-url-matrix.md).

### Submit a Test Request

```bash
# Direct HTTP (always works after `just up` when LOCAL_API_SCHEME is unset or http):
source scripts/daily/local-url.sh
curl_local -X POST "$(local_api_url /api/v1/observations)" \
  -H "Content-Type: application/json" \
  -d '{"source": "test", "timestamp": "2024-04-22T12:00:00", "data": {}}'
```

For additional API usage and request patterns, use Swagger via `bash scripts/daily/local-url.sh open /api/docs`.
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
lsof -i :6379      # Cache
lsof -i :443       # edge HTTPS
lsof -i :80        # edge HTTP
```

### HTTPS / Certificate Issues

**`ERR_CERT_AUTHORITY_INVALID` in Chrome/Chromium** — see [setup/local-https-setup.md](../setup/local-https-setup.md) for troubleshooting.

**`curl: (60) SSL certificate problem`** when running `curl`:
```bash
# The system CA trust store may not have mkcert's CA.
# Re-install the CA:
mkcert -install

# Check the CA is in the system store:
mkcert -CAROOT   # prints CA root directory
ls -la "$(mkcert -CAROOT)"
```

**Nginx returns "404 Not Found"** on `https://127.0.0.1/`:
- The root location block (`location /`) was commented out in `infra/nginx/nginx.conf`. Ensure it is uncommented and proxies to the dashboard upstream (or whichever service should serve the root path).
- After editing `infra/nginx/nginx.conf`, reload edge:
  ```bash
  docker compose exec edge nginx -s reload
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
4. **Enable HTTPS (optional)**: `bash scripts/setup/02-setup-local-https.sh` then ``
5. **Run tests**: `just test-unit` (fast) or `just test-integration` (requires PostgreSQL)
6. **Start the dev server**: `just dev`

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
