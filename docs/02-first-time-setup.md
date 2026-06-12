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

1. Open API docs: <http://localhost:8000/docs>
2. Open API docs via edge (if certs configured): <https://localhost/api/docs>

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
just up      # db, cache, broker, ingestor, dashboard (HTTP)
# For HTTPS parity (requires certs — see Step 6):
just up-https  # includes edge on :443
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

# Also available via edge (after just up with certs): https://localhost/api/docs

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

# Restart Docker Compose services after changing non-app config (e.g. Cache URL, DB port)
docker compose restart
# Note: if you changed DATABASE_URL and are running uvicorn directly (not in Docker),
# stop uvicorn (Ctrl+C) and restart it — docker compose restart does not affect it.
```

For the full env var matrix (all variables, defaults, CI/CD and deployment contexts), see
[Environment Setup](setup/environment-setup.md).

---

## Step 6 (Optional): Enable HTTPS for Local Parity

For maximum local → dev/prod parity, enable HTTPS via edge. This is optional since HTTP on `:8000` works for development.

### 6a. Install mkcert (one-time system install)

```bash
# macOS
brew install mkcert

# Ubuntu / Debian
sudo apt install mkcert libnss3-tools

# Fedora / RHEL
sudo dnf install mkcert nss-tools
```

> **Why `libnss3-tools`?** On Linux, Chrome/Chromium uses the NSS (Network Security Services) database for certificate trust, which is **separate from the system trust store**. The `libnss3-tools` package provides `certutil`, which `mkcert` needs in order to register its local CA with Chromium. Without it, Chrome will reject the certificate with `ERR_CERT_AUTHORITY_INVALID`.

### 6b. Install the local CA and generate certificates

```bash
# Install mkcert's local CA into system + browser trust stores
mkcert -install

# Generate certificates for localhost, 127.0.0.1, and *.local
bash scripts/setup/02-setup-local-https.sh
```

The script will create two files in `infra/certs/`:
- `localhost+2.pem` — the public certificate
- `localhost+2-key.pem` — the private key

These are mounted into the edge container at `/etc/nginx/certs/`.

### 6c. Start the stack with edge

```bash
# Start all services including edge (HTTPS on :443)
just up-https
```

### 6d. Verify HTTPS is working

```bash
# curl should show a valid TLS handshake (no -k needed if CA is trusted)
curl -v https://localhost/health

# Open API docs in browser
open https://localhost/api/docs
```

**Expected output after `just up-https`:**

```text
✓ All services running (db, cache, broker, ingestor, dashboard, edge)
✓ HTTPS available at https://localhost + https://localhost/api/*
```

### 6e. Certificate troubleshooting

If your browser shows **`ERR_CERT_AUTHORITY_INVALID`** or **`NET::ERR_CERT_AUTHORITY_INVALID`**:

1. **Install NSS tools** (Linux/Chrome only) — run once:
   ```bash
   sudo apt install libnss3-tools   # Debian/Ubuntu
   ```
2. **Re-install the CA** — this registers it with Chromium's NSS store:
   ```bash
   mkcert -install
   # Expected: ✓ installed in Firefox and/or Chrome/Chromium trust store
   ```
3. **Restart Chrome completely** — close all windows and reopen. A full restart is required because Chrome caches the NSS trust store at startup.
4. **Still broken?** Verify the CA is registered:
   ```bash
   certutil -L -d sql:$HOME/.pki/nssdb   # List trusted CAs (look for "mkcert")
   ```

After this step, access the application via HTTPS:

| URL                           | Purpose                                          |
| ----------------------------- | ------------------------------------------------ |
| `https://localhost/`          | Dashboard (via edge)                            |
| `https://localhost/api/docs`  | Swagger UI (interactive API docs)                |
| `https://localhost/api/redoc` | ReDoc (alternative API docs)                     |
| `http://localhost:8501/`      | Dashboard (Streamlit, direct — always available) |

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
PostgreSQL 17          localhost:5432   → Primary persistence (scorecards, observations, drift events)
Cache                  localhost:6379   → Scorecard TTL cache, WebSocket pub/sub, rate-limit backend
Redpanda (Kafka)       localhost:9092   → Drift events, async processing, DLQ
Ingestor API           localhost:8000   → FastAPI — probes, scorecards, agent enrichment
Dashboard (Streamlit)  localhost:8501   → Visual UI for scorecards, drift, live stream
```

**Optional services:**

```text
Floci (AWS emulator)   localhost:4566   → pre-deploy sandbox only: just sandbox-up
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

| URL                          | Purpose                                 |
| ---------------------------- | --------------------------------------- |
| `http://localhost:8000/`     | API (direct HTTP, always available)     |
| `http://localhost:8000/docs` | Swagger UI (direct HTTP)                |
| `http://localhost:8501/`     | Dashboard (Streamlit, always available) |

### Submit a Test Request

```bash
# Direct HTTP (always works after `just up`):
curl -X POST http://localhost:8000/api/v1/observations \
  -H "Content-Type: application/json" \
  -d '{"source": "test", "timestamp": "2024-04-22T12:00:00", "data": {}}'
```

For additional API usage and request patterns, use Swagger at `http://localhost:8000/docs` (direct) or `https://localhost/api/docs` (HTTPS via edge).
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

**`ERR_CERT_AUTHORITY_INVALID` in Chrome/Chromium** — see [Step 6e](#6e-certificate-troubleshooting) above.

**`curl: (60) SSL certificate problem`** when running `curl`:
```bash
# The system CA trust store may not have mkcert's CA.
# Re-install the CA:
mkcert -install

# Check the CA is in the system store:
mkcert -CAROOT   # prints CA root directory
ls -la "$(mkcert -CAROOT)"
```

**Nginx returns "404 Not Found"** on `https://localhost/`:
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
