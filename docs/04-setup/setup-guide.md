# Setup Guide

Local Docker Compose is the canonical runtime. The [`Justfile`](../../Justfile) owns command syntax;
this guide explains which mode to choose, what it proves, and where configuration lives.
The Docker-first `just dev-up` flow is the official onboarding path. Files under `.github/prompts/` are
historical agent prompts and are not setup instructions for new developers.

## Prerequisites

The supported developer workstation is Linux (Ubuntu) or macOS with Docker Engine/Desktop and
Compose v2, a running Docker daemon, Python 3.14.6, `uv`, `just`, Git, and `curl`. These are the
only host dependencies required for the default application workflow. Run `just doctor` before
creating `.env`; it checks the core tools and reports optional tooling as warnings.

For work spanning the sibling `api-observatory-infra` repository, use this ownership-based split:

| Work | Developer-machine dependencies |
| --- | --- |
| Application development and local Compose | Docker Engine/Desktop + Compose v2, Python 3.14.6, `uv`, `just`, Git, `curl` |
| Local database inspection | `psql`, `pg_dump`, `pg_restore` |
| Terraform or AWS infrastructure review | Terraform, TFLint, AWS CLI, `jq` |
| AWS Stage 0 host bootstrap | Full Ansible installed with `pipx`, `ansible-lint`, collections from `api-observatory-infra/ansible/requirements.yml`, and AWS Session Manager plugin |
| Kubernetes or emulator labs | Only when used: `kubectl`, Helm, k3d, or the relevant emulator |

Install Ansible as an isolated operator tool, not into this application's `uv` environment. With
the repositories checked out beside each other, install the infra collections with:

```bash
pipx install --include-deps ansible
pipx install ansible-lint
ansible-galaxy collection install -r ../api-observatory-infra/ansible/requirements.yml
```

Terraform, the PostgreSQL client tools, Ansible, AWS CLI, and the Session Manager plugin are optional
for normal application work. They become required only when the task owns the corresponding
infrastructure or operator action. Missing core application tools must be fixed before starting the
local stack.

Never read or commit a local `.env`. Copy the public, non-secret
[`.env.example`](../../.env.example), then generate local credentials privately.

## Quick Start

```bash
just doctor
cp .env.example .env
just generate-secrets
just dev-up
just dev-wait-ready
just db-migrate
just test-smoke
```

Run `just help-core` for the same focused command map after setup. It keeps cloud, Kubernetes,
security, and emulator recipes out of the first-task workflow.

After the quick start works, use the [local stack walkthroughs](../05-development/local-stack-walkthroughs.md)
to trace core, tenant/migration, and extended-stack behavior at increasing depth.

For first-use verification, use the dashboard at `http://127.0.0.1:8501`. The onboarding path does
not require copying credentials or tokens into a terminal. Use the API docs and authenticated curl
flows only when developing or testing an API-specific change.

The dashboard starts successfully with an empty database. Run `just db-auto-init` only when you want the
local admin account and example sources for a populated demo walkthrough.

For the authenticated demo path, run `just db-auto-init`, open the dashboard, and use the Login tab
with the local demo account `admin` / `admin123`. These credentials are disposable development
fixtures created by the seed recipe; never use them outside a local demo database. The same account
can authenticate API requests through `POST /api/v1/auth/token` when an API-specific task needs it.

Treat these as two separate dashboard states:

- **Empty dashboard:** confirms the UI and service wiring start correctly; no login or demo data is
  required.
- **Authenticated dashboard:** required for source management and other protected actions; run
  `just db-auto-init` for the local demo admin/source setup before using those features.

`just test-smoke` deliberately creates a small observation and leaves it in the local database so
the write/read path is proven. Treat that data as persistent developer data; use
`just db-reset --confirm DELETE` only for disposable demo environments.

`just generate-secrets` creates or rotates the local prod-like passwords and tokens in `.env` without
printing them. The [`Justfile`](../../Justfile) owns the remaining executable workflows.

`just dev-up` is the default HTTP workflow. Use `http://127.0.0.1:8000/api/docs` for the OpenAPI UI and
`http://127.0.0.1:8501` for the dashboard. HTTPS is a later, opt-in verification step for proxy,
cookie, redirect, WebSocket, and security-header testing: run
`bash scripts/setup/02-setup-local-https.sh`, then start the `ingress` profile as documented below.

## Supported Local Modes

| Mode | Entry point | Use |
| --- | --- | --- |
| Docker-first | `just dev-up` | Default HTTP containerized development stack |
| Inference | `just dev-up-inference` | Core stack plus inference and its dedicated PostgreSQL database |
| Full optional integration | `just dev-up-extended` | Inference stack plus Redis and Redpanda for a cross-integration task |
| Hot reload (optional) | `just dev` | Direct HTTP on host Uvicorn/Streamlit after Docker-first setup |
| Containerized watch (advanced) | Manual Compose Watch command below | Core containers with source sync and reload for Compose debugging |
| Monitoring | `just dev-up-monitoring` | Opt-in Prometheus, Grafana, Loki/Promtail, Tempo, Alertmanager, Mailpit |
| Cloud emulator | `CLOUD=<aws|azure|gcp> just cloud-sandbox-up` | Zero-cost provider-shaped API/IaC exercises, not real cloud behavior |
| Local Kubernetes | `just k8s-up` | Orchestration lab; Compose remains canonical |

The [`Justfile`](../../Justfile) documents companion stop, status, test, and teardown recipes. Real
AWS Stage 0 is **Decision** evidence and is handled by the sibling infra
[deployment guide](https://github.com/ivanprytula/api-observatory-infra/blob/main/docs/deployment/deployment-guide.md),
not by a local environment profile.

## HTTP and HTTPS Split

Use Docker-first HTTP for onboarding, day-to-day editing, local API debugging, and focused tests:
`just dev-up` serves the ingestor at `http://127.0.0.1:8000` and the dashboard at
`http://127.0.0.1:8501`. After that path works, `just dev` is an optional host-process hot-reload
mode with the same `.env` feature flags. It starts PostgreSQL only by default; run the explicit
`dev-up-cache` or `dev-up-broker` recipe before using those integrations. It is not a separate
onboarding requirement. Because `just dev` runs the host servers in the foreground, use two
terminals: keep `just dev` running in terminal 1, and run `dev-wait-ready`, migrations, and tests from
terminal 2.

### Manual Compose Watch

Use this advanced, containerized watcher only when debugging Compose-specific behavior such as
container reload, image rebuild, or service networking. It is not a replacement for `just dev` and
must not run at the same time as another local stack because it uses the same ports.

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --watch --build ingestor-db ingestor dashboard
```

Keep that command in terminal 1. In terminal 2, run `just dev-wait-ready`, focused migrations, and
tests. This watcher intentionally starts only the core services; use the explicit `dev-up-cache`,
`dev-up-broker`, `dev-up-inference`, or `dev-up-extended` paths when a task needs optional dependencies. Its ingestor
override applies pending ingestor migrations on startup, so use the native migration workflow when
authoring or reviewing schema changes.

Stop the watcher with Ctrl+C, then remove its containers/network without deleting named database
volumes:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
```

Use HTTPS when proving the public boundary: install developer-trusted certificates with
[`scripts/setup/02-setup-local-https.sh`](../../scripts/setup/02-setup-local-https.sh), then run
`docker compose --profile ingress up -d --build`. The Nginx edge redirects port 80 to HTTPS,
terminates TLS, and proxies the public API under `/api/`.

Use this explicit HTTPS sequence:

```bash
# Edit .env and set API_OBS_LOCAL_HTTPS=true before continuing.
bash scripts/setup/02-setup-local-https.sh
docker compose --profile ingress up -d --build
curl --fail https://127.0.0.1/api/health --insecure
```

Return to the normal HTTP stack with `docker compose --profile ingress down` followed by `just dev-up`.
The certificate script installs a local development CA and writes certificates under
`infra/certs/`; do not reuse these files for production or commit them.

Production always terminates TLS at its public ingress or load balancer. Internal container traffic
uses private Compose networking; adding end-to-end TLS or mTLS requires an explicit trust-boundary
requirement.

## Configuration Ownership

- [`.env.example`](../../.env.example) is a public, credential-free template.
- `.env` is ignored, generated locally, and contains passwords and signing/token secrets. The
  generator replaces it atomically with user-only permissions (`0600`); never commit or share it.
- [`services/ingestor/config.py`](../../services/ingestor/config.py) owns ingestor defaults,
  validation, feature flags, and secret classification.
- [`services/inference/config.py`](../../services/inference/config.py) and
  [`services/mcp/config.py`](../../services/mcp/config.py) own their service-specific settings.
- [`docker-compose.yml`](../../docker-compose.yml) owns service wiring, ports, profiles, and
  container-to-container addresses.

The local namespace is intentionally explicit: Docker images and containers use `api-obs-*`,
local `.env` controls use `API_OBS_*`, and physical database names use `api_obs_<service>`.
Inside a running service, conventional variables such as `DATABASE_URL` remain service-local and
are populated by Compose or cloud secret delivery.

Core operation requires PostgreSQL and authentication configuration. Redis, Redpanda, telemetry,
notifications, background workers, external AI providers, and demo routes remain optional or
feature-gated. Host processes use `127.0.0.1`; containers use Compose DNS names such as `ingestor-db`,
`cache`, and `broker`.

Local secrets may come from the ignored `.env`. Cloud secret delivery is infrastructure-owned; the
application only consumes environment variables declared by the
[deployment contract](../07-deployment/app-repo-contract.md).

For a local database client such as DBeaver or pgAdmin, use `127.0.0.1`, user `postgres`, and the
matching namespaced database/password pair: `5432` / `api_obs_ingestor` /
`API_OBS_INGESTOR_DB_PASSWORD` for the ingestor, or `5433` / `api_obs_inference` /
`API_OBS_INFERENCE_DB_PASSWORD` for inference. Obtain the password from your ignored `.env`; never
paste it into documentation, shell history, or committed client configuration.

For an interactive local terminal session, explicitly select the service with `just db-psql ingestor`
or `just db-psql inference`. Cloud database operations behind a VPN use native `psql` with an
infrastructure-supplied `DATABASE_URL`; the local helper deliberately cannot target cloud hosts.

## Service Map

Use this map to choose the smallest area to inspect for a task:

| Area | Owns | Start here |
| --- | --- | --- |
| `services/ingestor` | FastAPI API, PostgreSQL models/migrations, probes, scheduling, optional Redis/Redpanda integrations | `services/ingestor/main.py`, its routers, and `services/ingestor/tests/` |
| `services/dashboard` | Streamlit dashboard and user-facing views | `services/dashboard/ui/streamlit/` |
| `services/inference` | Optional embeddings, retrieval, and inference API with its dedicated database | `services/inference/` and `services/inference/tests/` |
| `services/mcp` | Local stdio MCP server for developer/agent workflows; not a cloud HTTP service | Follow [`services/mcp/README.md`](../../services/mcp/README.md), then run `uv run python -m services.mcp.main` |
| `libs/contracts` | Shared event and API contract definitions | `libs/contracts/` and contract tests |
| `tests/` | Repository-wide smoke, end-to-end, and cross-service checks | `tests/` |

Keep service-specific behavior in its owning service. Change shared contracts only when the
producer/consumer boundary actually changes, then run the focused contract tests as well.

### MCP Tasks Only

MCP is not part of core or extended-stack onboarding: it is a locally spawned stdio process, not a
Compose service or cloud HTTP deployment. Follow the [MCP service README](../../services/mcp/README.md)
only when a task changes MCP tools or its authenticated ingestor boundary. It covers the one-time
service-account setup, the separate ignored `services/mcp/.env`, the stdio launch command, and its
focused test suite.

## Runtime Shapes

Start with the smallest working stack:

```bash
just dev-up
```

This starts PostgreSQL (`ingestor-db`), the ingestor API, and the dashboard. Redis and Redpanda are not
started by default. The API is available at `http://127.0.0.1:8000`; the dashboard is at
`http://127.0.0.1:8501`. Run `docker compose down` when finished.

Stop without deleting data with:

```bash
docker compose stop
```

Use `docker compose down` when removing the local containers and network is desired. Do not add
`--volumes` unless you intentionally want to delete local database data.

`just db-reset --confirm DELETE` is disposable-demo tooling. It removes and recreates the ingestor
PostgreSQL container and its local named volume, then starts only the core stack; Redis, Redpanda,
and the separate inference database remain opt-in and untouched. Stop using it once you have
registered real observations, real API URLs, or any other data you want to keep. For that data,
stop/start containers without resetting volumes. After a reset, explicitly run `just dev-wait-ready`,
then `just db-migrate` and `just db-auto-init` when you need demo data.
Before any destructive database operation, create and verify a manual backup with
`bash infra/scripts/backup.sh`; do not proceed until the dump is known to be usable.

The setup commands are intentionally explicit: `dev-wait-ready` checks API readiness, `db-migrate` applies
Alembic migrations, `db-auto-init` requires that ready API and current migration head before creating the
local admin/demo sources, and `test-smoke` verifies the API and dashboard. Repeat only the steps relevant
to the change during daily development; do not rely on startup recipes to perform hidden waits, migrations,
or seeding.

Add only the capability a task needs. Inference uses its Compose profile, not an application feature
flag:

```bash
just dev-up-inference
just dev-wait-ready
just db-migrate
just db-inference-migrate
just dev-inference-ready
```

For an end-to-end task that needs all optional integrations, set
`API_OBS_CACHE_ENABLED=true` and `API_OBS_BROKER_ENABLED=true` in `.env`, then run
`just dev-up-extended`. It enables the Compose `cache`, `broker`, and `inference` profiles.

`db-inference-migrate` requires a healthy `inference-db`, then runs a disposable migration
container. The inference API process does not need to be healthy yet. Both readiness checks are
still required before using the full stack: `dev-wait-ready` proves the ingestor API, while
`dev-inference-ready` proves the inference API.

`dev-inference-ready` checks `http://127.0.0.1:8001/health`; `db-inference-migrate` applies the
inference service's separate Alembic history. Neither command is run implicitly by either inference
startup recipe.

| Capability | `.env` setting | Start command |
| --- | --- | --- |
| Redis integration | `API_OBS_CACHE_ENABLED=true` | Set the flag first, then `just dev-up-cache` |
| Broker integration | `API_OBS_BROKER_ENABLED=true` | Set the flag first, then `just dev-up-broker` |
| Inference and vector search | None | `just dev-up-inference` |
| OpenTelemetry | `API_OBS_OTEL_ENABLED=true` | `docker compose restart ingestor dashboard`, then `just dev-up-monitoring` |
| Full optional integration | `API_OBS_CACHE_ENABLED=true` and `API_OBS_BROKER_ENABLED=true` | `just dev-up-extended` |
| HTTPS ingress | `API_OBS_LOCAL_HTTPS=true` | `bash scripts/setup/02-setup-local-https.sh` then `docker compose --profile ingress up -d --build` |
| Full monitoring | `API_OBS_OTEL_ENABLED=true`, then restart application services | `just dev-up-monitoring` |

After changing a cache, broker, or telemetry flag in `.env`, start the matching dependency recipe
and restart only the ingestor so it receives the new values; the dashboard does not need to restart.
Inference uses its Compose profile instead. Keep service URLs different for host processes
(`127.0.0.1`) and Compose containers (`ingestor-db`, `cache`, `broker`, `inference`).

Redpanda is currently a producer-only integration in the application: the ingestor publishes
`observation.created` and `doc.scraped` events, but no production service in this repository
consumes them yet. The partition/consumer-group example under
[`labs/partitioning_sharding/`](../../labs/partitioning_sharding/) is an isolated learning lab,
not part of the normal local stack. Enable the broker when you need to verify event publication
or prepare that future consumer boundary; do not expect the dashboard or ingestor to drain a
Redpanda topic today.

OpenTelemetry is disabled by default. To collect local traces, set `API_OBS_OTEL_ENABLED=true` in `.env`,
restart only the application services, and then run:

```bash
docker compose restart ingestor dashboard
just dev-up-monitoring
```

Starting the monitoring UI alone
does not enable tracing in the application.

| Setup | Containers | What it proves | Operational cost |
| --- | --- | --- | --- |
| `just dev-up` | PostgreSQL, ingestor, and dashboard | API, persistence, and user interface | Lowest |
| `just dev-up-inference` | Core stack plus inference and its dedicated PostgreSQL database | Semantic search/RAG path | Moderate |
| `just dev-up-extended` | Inference stack plus Redis and Redpanda | Full optional integration | Higher |
| `just dev-up-monitoring` | Monitoring services added to an already-running stack | Focused local observability exercises | Highest |

Choose the smallest shape that proves the behavior you are working on. Cache, broker, telemetry,
AI, cloud emulators, backups, and notifications are opt-in capabilities, not baseline requirements.

Cloud-emulator workflows are an intentional exception to the explicit local sequence:
`cloud-sandbox-up` starts the selected emulator, applies migrations, and seeds disposable demo data
in one command. Do not use it for retained observations or real API sources.

## Optional Local Capabilities

- HTTPS/edge parity is owned by the Compose `ingress` profile and the local certificate setup
  script named in the [HTTP and HTTPS split](#http-and-https-split).
- Image/dependency scanning is owned by the security recipes in the
  [`Justfile`](../../Justfile) and [CI workflows](../../.github/workflows/).
- pgvector is provisioned by the inference database image and migration under
  [`services/inference/`](../../services/inference/).
- Performance and fault work starts from the
  [performance/failure worksheet](../05-development/performance-and-failure-lab.md), which links the
  maintained scripts.

Qdrant, a production frontend replacement, ECS/EKS, and real multi-cloud environments are not
active setup modes. Their adoption requires a trigger from the
[roadmap](../03-planning/mvp-roadmap.md).

## Verification and Troubleshooting

Use `just doctor`, service health/readiness endpoints, and the focused test recipes in the
[`Justfile`](../../Justfile). If startup fails, inspect native Compose state and logs first:

```bash
docker compose ps
docker compose logs --tail=100 <service>
```

Then check migrations and the owning settings module rather than copying command sequences into this
guide.

If `dev-wait-ready` does not complete promptly, stop it with Ctrl+C and inspect the running services
before retrying:

```bash
docker compose ps
docker compose logs --tail=100 ingestor-db ingestor
```

For the development loop and proof selection, continue with
[development workflows](../05-development/dev-workflows.md).
