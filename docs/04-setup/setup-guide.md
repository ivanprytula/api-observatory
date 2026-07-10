# Setup Guide

Track: B — Engineering Execution

Consolidated setup reference. For first-time bootstrap, start at [Quick Start](#quick-start) below.

---

## System Requirements

### Ubuntu/Debian Packages

```bash
sudo apt-get install -y postgresql-client redis-tools docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin gdal-bin graphviz curl jq git
```

### Python Tooling (uv)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync                            # install all project dependencies
uv tool install awscli-local       # for local AWS emulation
```

### Verification

Run `just doctor` for automated system check, or verify manually:

```bash
docker --version && docker compose version && python3 --version && uv --version
```

### Docker Permissions

```bash
sudo usermod -aG docker "$USER"
# Log out and back in
```

### Local Artifacts

All local state lives in `.local-dev/` (gitignored). This directory is created automatically by `just doctor`.

---

## Quick Start

```bash
just doctor            # verify tooling, create .local-dev/
cp .env.example .env   # create local configuration
uv sync                # sync Python deps
just up                # start PostgreSQL + Cache + Redpanda + ingestor + Streamlit
just migrate           # apply Alembic migrations
```

### Verify

```bash
curl -sf http://127.0.0.1:8000/health          # expect {"status":"healthy"}
uv run pytest tests/unit/ -q                     # fast unit test pass
```

For an interactive demo, run `just init` and follow the printed `curl` commands to register an admin user, sign in, and register a demo source.

---

## Environment Variables

### Core Variables (Required)

| Variable | Purpose | Example |
|----------|---------|---------|
| `DATABASE_URL` | SQLAlchemy async URL | `postgresql+asyncpg://postgres:postgres@db:5432/api_observatory` |
| `ENVIRONMENT` | Runtime mode | `development`, `staging`, `production` |
| `SERVICE_VERSION` | Service provenance | `0.1.0` or `git describe --tags` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `LOG_FORMAT` | Log format | `text` (dev) / `json` (prod) |

### Auth Variables

| Variable | Purpose |
|----------|---------|
| `JWT_SECRET` | HS256 signing key (≥32 chars) |
| `JWT_EXPIRY_MINUTES` | Access token TTL (default 30) |
| `JWT_REFRESH_TTL_DAYS` | Refresh token TTL (default 7) |
| `API_V1_BEARER_TOKEN` | Simple bearer token for v1 endpoints |
| `INTERNAL_JWT_SECRET` | M2M service-to-service auth |

### Feature Flag Variables

| Variable | Effect |
|----------|--------|
| `CACHE_ENABLED=true` | Enable Cache: scorecard cache, pub/sub, rate limiting, agent checkpointer |
| `BROKER_ENABLED=true` | Enable Redpanda/Kafka for drift event streaming |
| `OTEL_ENABLED=true` | Enable OpenTelemetry tracing export to Jaeger |
| `SENTRY_ENABLED=true` | Enable Sentry/GlitchTip exception tracking |
| `OPENAI_ENABLED=true` | Enable LangGraph agent (requires `OPENAI_API_KEY`) |
| `NOTIFICATIONS_ENABLED=true` | Enable multi-channel alert dispatch |
| `BACKGROUND_WORKERS_ENABLED=true` | Enable in-process background worker pool |

### DB Connection Pool

| Variable | Default | Meaning |
|----------|---------|---------|
| `DB_POOL_SIZE` | 5 | Connections kept open |
| `DB_MAX_OVERFLOW` | 10 | Extra connections on burst |
| `DB_POOL_TIMEOUT` | 30s | Wait for available connection |
| `DB_POOL_RECYCLE` | 1800s | Connection refresh interval |

### Secrets Management

**Local dev:** Copy `.env.example` → `.env`, set dummy secrets. Never commit `.env`.

**Production:** Use AWS Secrets Manager / SSM Parameter Store. In ECS: use task definition Secrets section. In CI: use GitHub Secrets with masking.

**Rotation:** Rotate long-lived secrets every 90 days. Use `JWT_PREVIOUS_SECRETS` for zero-downtime JWT rotation.

---

## Local URL Matrix

The `LOCAL_API_SCHEME` environment variable switches between two modes:

| Mode | API base | API docs | Dashboard | WebSocket | Bruno baseUrl |
|------|----------|----------|-----------|-----------|---------------|
| Direct HTTP | `http://127.0.0.1:8000` | `http://127.0.0.1:8000/docs` | `http://127.0.0.1:8501` | `ws://127.0.0.1:8000` | `http://127.0.0.1:8000` |
| Edge HTTPS | `https://127.0.0.1/api` | `https://127.0.0.1/api/docs` | `https://127.0.0.1/` | `wss://127.0.0.1` | `https://127.0.0.1/api` |

All URLs use `127.0.0.1` (IPv4 literal) instead of `localhost` to bypass DNS resolution.

**Shared helper:** `bash scripts/daily/local-url.sh --help` prints URLs for the current mode.

---

## AWS Sandbox Profile (Floci)

One-time setup for local AWS emulation:

```bash
# ~/.aws/credentials
[sandbox]
aws_access_key_id     = test
aws_secret_access_key = test

# ~/.aws/config
[profile sandbox]
region = eu-central-1
```

Then point the AWS CLI at the emulator and verify:

```bash
export AWS_PROFILE=sandbox
export AWS_ENDPOINT_URL=http://localhost:4566   # floci-aws (docker-compose.yml `aws` profile)
aws sts get-caller-identity
```

---

## What Just Happened? (Services Started)

`just up` starts the core MVP stack:

- **PostgreSQL 17** `:5432` — Primary persistence
- **Cache 7** `:6379` — Scorecard cache, WebSocket pub/sub, rate-limit backend
- **Redpanda (Kafka)** `:9092` — Drift events, async processing, DLQ
- **Ingestor API** `:8000` — FastAPI: probes, scorecards, agent enrichment
- **Dashboard (Streamlit)** `:8501` — Visual UI for scorecards, drift, live stream

### Database Schema

Alembic migrations create tables for: observations, pipeline jobs, source profiles, contract snapshots, drift events, users, API keys, security audit events, abuse signals, messaging infrastructure.

---

## Related

- [Environment / Stack Matrix](../01-intro/environment-stack-matrix.md) — deployment scenarios and env var matrix
- [Commands Reference](../05-development/dev-workflows.md) — canonical command catalog
- [Daily Development](../05-development/dev-workflows.md) — workflow intent and sequence
