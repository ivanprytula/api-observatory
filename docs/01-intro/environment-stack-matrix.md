# Environment / Stack Matrix

This matrix maps the supported deployment scenarios to the active services, required environment variables, and the recommended Justfile entrypoint. Use it when you need to know “what stack am I working against right now”, or when you want to move data between local and cloud environments safely.

## Scenarios

| Scenario | Infra | Postgres | S3 / object store | Messaging | Cache / cache | Ingestion runs in | Typical goal |
|---|---|---|---|---|---|---|---|
| `local-docker` | Docker Compose only | `api-obs-db` (:5432) | none (MinIO unused by default) | `api-obs-broker` | `api-obs-cache` | `api-obs-ingestor` container | Full offline dev, API/tinker work |
| `local-uvicorn` | Docker Compose infra + host `uvicorn` | `api-obs-db` container | none | `api-obs-broker` | `api-obs-cache` | host process (hot reload) | Fast inner-loop code changes |
| `local-expanded-pg` | Docker Compose (DB grown, volumes preserved) | `api-obs-db` container with large volume | none | optional | optional | container or host | Local DB grown to prod-like size for load testing; can drop messaging/cache to save RAM |
| `sandbox` | Floci AWS emulator + Docker Compose | `api-obs-db` container | Floci S3 (`127.0.0.1:4566`) | Floci SQS adapter | none by default | host `uvicorn` (or container) | Validate AWS-shaped config; Terraform `TF_ENV=sandbox`; no real cloud charges |
| `dev` | Real AWS (ECS/Fargate + RDS + ElastiCache/MSK/ECR) | AWS RDS | AWS S3 | AWS MSK (optionally disabled via `enable_messaging=false`) | AWS ElastiCache | ECS Fargate task | First real cloud loop; smoke checks; keep cost low |
| `prod` | Real AWS (production account; multi-AZ) | AWS RDS multi-AZ | AWS S3 | AWS MSK | AWS ElastiCache multi-node | ECS Fargate (auto-scaling) | Customer traffic; strict promotion policy |
| `local-against-dev` | Host uvicorn or Docker container, AWS env sourced | AWS RDS (via `DATABASE_URL`) | AWS S3 | AWS MSK (rare locally) | AWS ElastiCache (or empty) | host | Troubleshoot against real staging data; dump prod data via `pg_dump` / `aws s3 cp` |

---

## Environment variable matrix (quick reference)

### Hard boundaries (must match scenario)

| Variable | local-docker | local-uvicorn | local-expanded-pg | sandbox | dev | prod | local-against-dev |
|---|---|---|---|---|---|---|---|
| `ENVIRONMENT` | `development` | `development` | `development` | `development` (or explicit `sandbox`) | `development` (dev), `staging` | `production` | `development` |
| `DATABASE_URL` | Compose-injected `postgresql+asyncpg://postgres:…@db:5432/…` | Compose-injected or host-local | Compose-injected | Compose-injected | AWS RDS DSN | AWS RDS DSN (multi-AZ) | AWS RDS DSN |
| `DATABASE_HOST` (implicit) | `db` | `db` or `localhost` | `db` | `db` | `<rds-endpoint>` | `<rds-endpoint>` | `<rds-endpoint>` |
| `CACHE_URL` | `redis://cache:6379` | `redis://cache:6379` | optional (unset) | `redis://cache:6379` | ElastiCache endpoint | ElastiCache endpoint | ElastiCache endpoint (or empty) |
| `BROKER_URL` | `broker:29092` | `broker:29092` | optional (unset) | `broker:29092` | MSK bootstrap | MSK bootstrap | none |
| `LOG_FORMAT` | `json` (container) / `text` (host) | `text` | `text` | `json` | `json` | `json` | `json` |
| `AWS_PROFILE` | unset / empty | unset / empty | unset / empty | `sandbox` (from `scripts/aws-env.sh`) | named dev profile (e.g. `data-zoo-dev`) | prod profile | dev or prod profile — **danger** |
| `AWS_ENDPOINT_URL` | unset | unset | unset | `http://127.0.0.1:4566` | unset | unset | unset (except sandbox) |
| `AWS_ACCESS_KEY_ID` | unset | unset | unset | `test` | real IAM role / named profile | real IAM role / named profile | real creds |
| `TF_ENV` | `sandbox` (default) | `sandbox` | `sandbox` | `sandbox` | `dev` | N/A | N/A |

### Object storage mode

The ingestor service does **not** use `boto3`. Object reads/writes in the service go through the MinIO Python client in `services/ingestor/storage/minios3.py`. AWS CLI and Terraform still use real `boto3` under the hood; what changes per scenario is the endpoint and credentials.

| Variable | local-* | sandbox | dev | prod |
|---|---|---|---|---|
| `MINIO_ENDPOINT` | `127.0.0.1:9000` (if MinIO is spun up) | `127.0.0.1:4566` (S3 path-style via Floci) | real S3 endpoint (`s3.<region>.amazonaws.com`) | real S3 endpoint |
| `AWS_S3_BUCKET` | `api-observatory-local` | `api-observatory-local` | `<project>-dev-data` | `<project>-prod-data` |
| `S3_FORCE_PATH_STYLE` | `true` (MinIO / Floci S3) | `true` | `false` | `false` |

### Optional toggles (drop services to save resources)

| Variable | When to set | Effect |
|---|---|---|
| `CACHE_ENABLED=false` | Local scenarios where you want to drop Cache to save RAM | Disables cache layer; app falls back to DB reads |
| `BROKER_ENABLED=false` | `local-expanded-pg`, dev with `enable_messaging=false` | Disables Kafka producer path; events stay in-process/DB |
| `KAFKA_STRANGLER_ADAPTER_ENABLED=false` | Do not use strangler | Use direct producer path (default) |
| `MONGO_ENABLED=false` | Always, for now | MongoDB module unattached |
| `OTEL_ENABLED=false` | Local unless debugging tracing | No OTLP export |
| `SENTRY_ENABLED=false` | Local unless debugging errors | No Sentry init |
| `BACKGROUND_WORKERS_ENABLED=false` | Light local testing | No in-process background worker pool |

---

## Justfile entrypoints by scenario

| Recipe | Scenario | What it actually touches |
|---|---|---|
| `just up` | `local-docker` | stops nothing, brings up Compose stack + stale stack check |
| `just dev` | `local-uvicorn` | Compose infra + `uvicorn` + stale stack check |
| `just db-reset` | `local-docker` (reset) | `docker compose rm -sfv ingestor db` then restart + wait |
| `just floci-up` | `sandbox` | Floci + S3/SQS seed + Compose infra + migrations + admin/demo seed |
| `just floci-dev` | `sandbox` | Floci env + Compose infra + `uvicorn` |
| `just floci-validate` | `sandbox` | Floci health + S3 + SQS + optional API health |
| `just floci-test` | `sandbox` | Floci + infra + AWS integration tests |
| `TF_ENV=dev just tf apply` | `dev` | Terraform dev target |
| `just psql-safe db-host=db` | any | blocks `*.rds.amazonaws.com` / `*.amazonaws.com` |
| `just pg-dump` | local Compose | dumps `api_observatory` to `.local-dev/dumps/…sql` |
| `just pg-restore <file>` | local Compose | drops schema, restores |
| `just pg-restore-from-s3 s3://…` | local Compose | fetches gzipped dump from S3, restores |
| `just s3-dump-local bucket=X dest=Y` | local + sandbox | mirrors bucket to local dir |
| `just s3-restore-to-remote bucket=X src=Y` | local + sandbox | uploads local dir to bucket |

---

## Scenario switching checklist

1. **Identify the destination stack** using the table above.
2. **Run `just stack-info`** (or any recipe that prints the banner) and confirm Cloud backend, Postgres host, and `TF_ENV`.
3. **Set / unset AWS env**:
   - Local: `unset AWS_PROFILE AWS_ENDPOINT_URL AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY` (or comment out `source scripts/aws-env.sh`).
   - Sandbox: `source scripts/aws-env.sh` (sets `AWS_PROFILE=sandbox`, `AWS_ENDPOINT_URL=http://127.0.0.1:4566`, test creds).
   - Dev/prod: use the named profile that matches the target account.
4. **Verify DATABASE_URL**:
   - Local: Compose injects it automatically.
   - Cloud: read from AWS Secrets Manager / SSM Parameter Store; never hardcode.
5. **Verify the safety recipe**:
   - `just psql-safe` must succeed against the local `db` and block RDS hostnames.
   - `just pg-dump` must write to `.local-dev/dumps/`.
6. **If moving prod data locally**: use `just pg-restore-from-s3` or `pg_dump` from an RDS bastion, then validate the local copy with `just psql-safe`.

---

## Safety guards (hard rules)

- `just psql-safe` refuses to open an interactive shell against hostnames ending in `.rds.amazonaws.com` or `.amazonaws.com`. Use direct `psql "$DATABASE_URL"` only when you explicitly want remote access, and confirm the target first.
- `EXPLAIN ANALYZE` integration tests are opt-in only via `ALLOW_EXPLAIN_ANALYZE=true`. They never run in CI or against remote databases.
- Never run `EXPLAIN ANALALYZE` (or any unparameterized ad-hoc SQL) against remote RDS — it executes synchronously on the production compute and can cause unexpected load or lock contention.
