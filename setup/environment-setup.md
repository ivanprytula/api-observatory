# Environment variables and secret guidance

This document lists all environment variables used by the project, grouped by category, with guidance for where to store secrets (local `.env` vs production secret manager / GitHub Secrets).

## Summary

- Local development: copy `.env.example` -> `.env` and set the values you need. Do NOT commit `.env` to source control.
- Production: inject secrets via your platform (ECS task definition, Kubernetes Secret, environment variables from Vault, GitHub Secrets in CI). Do not store production secrets in the repo.
- Feature flags: some variables enable optional features (Cache, Kafka, OpenAI). If unsure, use the defaults in `.env.example`.

## How to use

1. Copy the example: `cp .env.example .env`
2. Edit `.env` with secure values for secrets (JWT secret, OpenAI key, DB password).
3. For CI: add critical secrets to repository secrets (e.g., `OPENAI_API_KEY`, `SENTRY_DSN`, `AWS_*`, `JWT_SECRET`), and use CI job masking / secret injection.

## Core variables (required for full-stack dev)

See [services/ingestor/config.py](../../services/ingestor/config.py) for the canonical Settings class.

- **`DATABASE_URL`** — SQLAlchemy async URL (example: `postgresql+asyncpg://postgres:postgres@localhost:5432/api_observatory`). Required when running with Docker Compose and integration tests. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`ENVIRONMENT`** — environment name (`development`, `staging`, `production`). Controls some runtime behaviors. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`LOG_LEVEL`** — application logging level (e.g. `INFO`, `DEBUG`, `WARNING`). Default: `INFO`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`LOG_FORMAT`** — logging format (`text` or `json`). Default: `text`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))

## Database Connection Pool

Adjust based on expected load and PostgreSQL max_connections:

- **`DB_POOL_SIZE`** — Number of connections to keep open. Default: `5`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`DB_MAX_OVERFLOW`** — Extra connections beyond pool_size when demand spikes. Default: `10`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`DB_POOL_TIMEOUT`** — Seconds to wait for available connection before raising an error. Default: `30`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`DB_POOL_RECYCLE`** — Recycle connections after X seconds to avoid stale connections. Default: `1800` (30 min). (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`DB_ECHO`** — Enable SQL query logging. Default: `false`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))

## Authentication & API

### v1 API (Token-based)

- **`API_V1_BEARER_TOKEN`** — Simple bearer token for v1 endpoints. Endpoints require `Authorization: Bearer <token>` header. Rotate in staging/production. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`TOKEN_EXPIRY_HOURS`** — Session token expiration in hours. Default: `24`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))

### v2 API (JWT)

- **`JWT_SECRET`** — HS256 secret used for v2 JWT tokens. MUST be >= 32 chars and kept secret. Auto-generated at startup if not set. In production, store in Vault/GCP Secret Manager/AWS Secrets Manager or GitHub Secrets. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`JWT_PREVIOUS_SECRETS`** — Comma-separated previous JWT signing secrets accepted for token verification during rotation. New tokens are always signed with JWT_SECRET. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`JWT_ALGORITHM`** — JWT signing algorithm. Default: `HS256`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`JWT_EXPIRY_MINUTES`** — JWT access token expiration in minutes. Default: `30`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`JWT_REFRESH_TTL_DAYS`** — Refresh token time-to-live in days. Default: `7`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))

### Internal Service Auth (M2M)

- **`INTERNAL_JWT_SECRET`** — Shared secret for service-to-service JWT signing. Required on internal-only routes. Set via env variable or Secrets Manager. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))

### Documentation Protection

- **`DOCS_USERNAME`** — Username for `/docs` endpoint HTTP Basic auth. If None, docs are public. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`DOCS_PASSWORD`** — Password for `/docs` endpoint HTTP Basic auth. If None, docs are public. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))

## Cache / WebSocket

- **`CACHE_ENABLED`** — Enable Cache-backed features (scorecard cache, WebSocket pub/sub, rate limiting, agent checkpointing). Default: `false`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`CACHE_URL`** — Cache connection URL. Example: `redis://localhost:6379/0` or `redis://cache:6379/0` (Docker network). Default: `redis://localhost:6379/0`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))

## Event Broker / Redpanda (optional)

- **`BROKER_ENABLED`** — Enable event streaming to Redpanda/Kafka. Default: `false`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`BROKER_URL`** — Broker bootstrap servers (comma-separated). Example: `localhost:9092` (host) or `broker:29092` (Docker network). Default: `localhost:9092`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`KAFKA_STRANGLER_ADAPTER_ENABLED`** — Enable strangler adapter path for broker publishing. Default: `false`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))

## MongoDB (optional)

- **`MONGO_ENABLED`** — Enable MongoDB storage. Default: `false`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`MONGO_URL`** — MongoDB connection URL. Default: `mongodb://localhost:27017`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`MONGO_DB_NAME`** — MongoDB database name. Default: `datazoo`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))

## OpenTelemetry (distributed tracing)

- **`OTEL_ENABLED`** — Enable OpenTelemetry tracing export to Jaeger/collector. Default: `false`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`OTEL_ENDPOINT`** — OTLP gRPC endpoint. Example: `http://localhost:4317` or `http://jaeger:4317` (Docker network). Default: `http://localhost:4317`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`OTEL_SERVICE_NAME`** — Service name shown in Jaeger/OTel collector UI. Default: `ingestor`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))

## Sentry / GlitchTip (error tracking)

- **`SENTRY_ENABLED`** — Enable Sentry SDK initialization. Default: `false`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`SENTRY_DSN`** — Sentry DSN or GlitchTip DSN URL. Keep secret in production. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`SENTRY_TRACES_SAMPLE_RATE`** — Performance trace sampling rate (0.0–1.0). Default: `0.1`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`SENTRY_PROFILES_SAMPLE_RATE`** — Profiling sample rate (0.0–1.0). Default: `0.0`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`SENTRY_SEND_DEFAULT_PII`** — Whether Sentry should send default PII context. Default: `false`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))

## Background Workers (Pillar 5)

- **`BACKGROUND_WORKERS_ENABLED`** — Enable in-process background worker queue for large batch ingestion. Default: `false`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`BACKGROUND_WORKER_COUNT`** — Number of async worker tasks consuming the queue. Default: `2`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`BACKGROUND_WORKER_QUEUE_SIZE`** — Maximum queued jobs before rejecting new submissions. Default: `200`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`BACKGROUND_MAX_TRACKED_TASKS`** — Maximum completed task statuses kept in memory. Default: `500`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))

## Notifications & Alerting (Pillar 8)

- **`NOTIFICATIONS_ENABLED`** — Enable notification dispatching for operational events. Default: `false`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`NOTIFICATION_DEFAULT_CHANNELS`** — Comma-separated default channels: `slack`, `telegram`, `webhook`, `email`. Default: `slack,telegram`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`NOTIFICATION_HTTP_TIMEOUT_SECONDS`** — HTTP timeout for notification provider calls. Default: `10`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))

### Slack Integration

- **`NOTIFICATION_SLACK_WEBHOOK_URL`** — Slack incoming webhook URL for channel alerts. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))

### Telegram Integration

- **`NOTIFICATION_TELEGRAM_BOT_TOKEN`** — Telegram bot token for chat notifications. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`NOTIFICATION_TELEGRAM_CHAT_ID`** — Telegram chat ID for target channel/group/user. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))

### Generic Webhook

- **`NOTIFICATION_WEBHOOK_URL`** — Generic webhook destination for alert payloads (e.g., Jira automation). (Source: [services/ingestor/config.py](../../services/ingestor/config.py))

### Email Integration (Resend)

- **`NOTIFICATION_EMAIL_PROVIDER`** — Transactional email provider. Default: `resend`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`NOTIFICATION_RESEND_API_KEY`** — Resend API key for email delivery. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`NOTIFICATION_EMAIL_FROM`** — Sender email address for notification emails. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`NOTIFICATION_EMAIL_TO`** — Comma-separated recipient emails for operational alerts. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))

## Embeddings & Vector Search (Pillar 9)

- **`INFERENCE_URL`** — Base URL for the inference service (embeddings/semantic search). Default: `http://localhost:8001`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`VECTOR_SEARCH_COLLECTION`** — Default collection used for semantic record search. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`VECTOR_SEARCH_HTTP_TIMEOUT_SECONDS`** — HTTP timeout for AI gateway index and search requests. Default: `30`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`SCRAPER_TIMEOUT`** — Timeout for HTTP scrapers. Default: `30`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))

## LLM Integration (OpenAI)

- **`OPENAI_ENABLED`** — Enable OpenAI-based record analysis. Requires OPENAI_API_KEY. Default: `false`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`OPENAI_API_KEY`** — OpenAI API key for record analysis. Keep secret! (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`OPENAI_MODEL`** — OpenAI model for analysis. Default: `gpt-4o-mini`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))
- **`OPENAI_MODEL_DEEP`** — OpenAI model for deep analysis. Default: `gpt-4o`. (Source: [services/ingestor/config.py](../../services/ingestor/config.py))

## AWS & S3 Backup

- **`BACKUP_STORAGE`** — Storage backend: `local`, `s3`, or `both`. Default: `local`. (Source: [.env.example](../../.env.example))
- **`BACKUP_S3_BUCKET`** — S3 bucket for backups. (Source: [.env.example](../../.env.example))
- **`BACKUP_S3_PREFIX`** — S3 prefix path within bucket. (Source: [.env.example](../../.env.example))
- **`AWS_ENDPOINT_URL`** — Set to `http://localhost:4566` for Floci/localstack. Leave empty for real AWS. (Source: [.env.example](../../.env.example))
- **`AWS_ACCESS_KEY_ID`** — AWS access key (required for S3 backup to real AWS). (Source: [tests/e2e/test_floci_integration.py](../../tests/e2e/test_floci_integration.py))
- **`AWS_SECRET_ACCESS_KEY`** — AWS secret key (required for S3 backup to real AWS). (Source: [tests/e2e/test_floci_integration.py](../../tests/e2e/test_floci_integration.py))
- **`AWS_REGION`** — AWS region. Default: `us-east-1` in tests. (Source: [tests/e2e/test_floci_integration.py](../../tests/e2e/test_floci_integration.py))

## Testing

- **`DATABASE_URL_TEST`** — Test database URL. Examples: `sqlite+aiosqlite:///:memory:` (fast, in-memory) or `postgresql+asyncpg://...` (full integration test). (Source: [tests/conftest.py](../../tests/conftest.py))

## CI/CD & GitHub Actions

- **`GITHUB_EVENT_PATH`** — GitHub Actions event payload path (used by dependabot gate). (Source: [scripts/ci/dependabot_age_gate.py](../../scripts/ci/dependabot_age_gate.py))
- **`GITHUB_TOKEN`** — GitHub API token (used by CI scripts). (Source: [scripts/ci/dependabot_age_gate.py](../../scripts/ci/dependabot_age_gate.py))

## GlitchTip (local monitoring — optional)

- **`GLITCHTIP_DB_PASSWORD`** — GlitchTip database password. Keep secret for shared dev instances. (Source: [.env.example](../../.env.example))
- **`GLITCHTIP_SECRET_KEY`** — GlitchTip Django secret key (>= 50 random chars). (Source: [.env.example](../../.env.example))
- **`GLITCHTIP_DOMAIN`** — GlitchTip service domain. Default: `http://localhost:8010`. (Source: [.env.example](../../.env.example))

## Service URLs (for dashboard & frontend)

- **`INGESTOR_URL`** — Ingestor API base URL. Default: `http://localhost:8000`. (Source: [streamlit_app.py](../../services/dashboard/streamlit_app.py))

## Keycloak / OIDC (optional)

The project currently uses JWT and a simple token-based flow. If you integrate Keycloak or another OIDC provider:

- **`OIDC_ISSUER`** or **`KEYCLOAK_ISSUER`** — OIDC issuer URL (e.g., `https://auth.example.com/realms/myrealm`).
- **`OIDC_CLIENT_ID`** or **`KEYCLOAK_CLIENT_ID`** — OIDC client identifier.
- **`OIDC_CLIENT_SECRET`** or **`KEYCLOAK_CLIENT_SECRET`** — OIDC client secret (store in Secrets Manager).
- **`OIDC_INTROSPECTION_URL`** — Token introspection endpoint (if using introspection-based validation).

## Secrets management best practices

### Local Development

- Do NOT commit `.env` to git. Add `.env` to `.gitignore` (already present in repo templates).
- Use dummy secrets in local `.env` (e.g., `JWT_SECRET=dev-secret-at-least-32-chars-long`).
- Rotate secrets before pushing to shared dev instances.

### Production & Staging

- Use a secret manager: Vault, AWS Secrets Manager, GCP Secret Manager, or HashiCorp Cloud Platform (HCP).
- In ECS: use task definition Secrets section; inject via AWS Secrets Manager reference.
- In Kubernetes: use Secret objects with sealed-secrets or external-secrets operator.
- In GitHub Actions: add secrets under repository Settings → Secrets → Actions. Reference via `secrets.SECRET_NAME`.
- Enable secret masking in CI logs: `add-mask` for sensitive values.

### Secret Rotation

- Rotate long-lived secrets every 90 days.
- For JWT rotation: use `JWT_PREVIOUS_SECRETS` to accept old tokens during the rotation window.
- Monitor for leaked credentials: run `git-secrets` or `truffleHog` in CI.

### Audit & Monitoring

- Enable CloudTrail (AWS) or Activity Logs (GCP) to track secret access.
- Implement alerting for unauthorized access attempts.
- Log all secret rotations and changes.

## Quick setup checklist

```bash
# Local development
cp .env.example .env
# Edit .env: set DATABASE_URL, JWT_SECRET, OPENAI_API_KEY if using agent
bash scripts/setup/03-verify-system-requirements.sh
just up

# Run tests (no secrets needed for unit tests)
uv run pytest tests/unit/ -q

# Start services
just up   # or: just sandbox-up (for Floci/AWS sim)

# API access
curl http://localhost:8000/health
```

For CI/CD: add the following as repository secrets (Settings → Secrets → Actions):

- `OPENAI_API_KEY` (optional, only if using agent)
- `SENTRY_DSN` (optional, for error tracking)
- AWS credentials if pushing to ECR or deploying to ECS
