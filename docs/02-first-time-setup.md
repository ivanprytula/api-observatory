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
just init                   # print curl commands for manual bootstrap
```

**Expected output:**

```sh
✓ Services healthy
✓ Database schema initialized
```

Next steps — run the 4 commands from `just init` to register an admin user, sign in, and register a demo source:

```bash
# 1. Register as admin
curl -X POST http://127.0.0.1:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123","email":"admin@example.com","role":"admin"}'

# 2. Sign in, save token
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=admin&password=admin123' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 3. Register a demo source
curl -X POST http://127.0.0.1:8000/api/v1/sources \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"httpbin","base_url":"https://httpbin.org","health_check_path":"/get","probe_interval_seconds":10}'

# 4. Verify
curl http://127.0.0.1:8000/api/v1/sources \
  -H "Authorization: Bearer $TOKEN"
```

For HTTPS parity, set `LOCAL_API_SCHEME=https just up` (requires mkcert certs — see Step 6).

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
docker compose ps
curl -sf http://127.0.0.1:8000/health          # expect {"status":"healthy"}
uv run pytest tests/unit/ -q                     # expect 192 passed, 10 skipped
```

---

## Step 5 (Optional): Enable HTTPS for Local Parity

Run `bash scripts/setup/02-setup-local-https.sh` to generate mkcert certs, then start with `LOCAL_API_SCHEME=https just up`.

---

## Step 6 (Optional): Customize Environment

See [setup/environment-setup.md](../setup/environment-setup.md) for environment variables, defaults, and CI/CD contexts.

---

## Step 7 (When Ready): CI/CD and Real AWS Access

Requires an AWS account, OIDC trust, and GitHub secrets. Set variables with `gh`:

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

```bash
# API docs (Swagger)
curl http://127.0.0.1:8000/docs

# Submit a test observation
curl -X POST http://127.0.0.1:8000/api/v1/observations \
  -H "Content-Type: application/json" \
  -d '{"source": "test", "timestamp": "2024-04-22T12:00:00", "data": {}}'
```

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

1. **Run tests**: `just test-unit` (fast) or `uv run pytest tests/ -v`
2. **Start the dev server with hot-reload**: `just dev`
3. **Enable HTTPS (optional)**: run `bash scripts/setup/02-setup-local-https.sh` then `LOCAL_API_SCHEME=https just up`
4. **Configure environment**: copy `.env.example` to `.env` and edit as needed
