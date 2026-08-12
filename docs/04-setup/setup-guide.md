# Setup Guide

Local Docker Compose is the canonical runtime. The [`Justfile`](../../Justfile) owns core named
recipes, while [`just/labs.just`](../../just/labs.just) owns explicitly invoked disposable labs.
This guide explains which mode to choose, what it proves, and where native commands are clearer.
The Docker-first `just dev-up` flow is the official onboarding path. Files under `.github/prompts/` are
historical agent prompts and are not setup instructions for new developers.

## Quick Start

Follow the [Canonical Onboarding and Delivery Checklist](../05-development/onboarding-and-delivery-checklist.md) for the complete first-time setup sequence. This guide explains which mode to choose, what it proves, and where configuration lives.

## Supported Local Modes

| Mode | Entry point | Use |
| --- | --- | --- |
| Docker-first | `just dev-up` | Default HTTP containerized development stack |
| Inference | `just dev-up-inference` | Core stack plus inference and its dedicated PostgreSQL database |
| Full optional integration | `just dev-up-extended` | Inference stack plus Redis and Redpanda for a cross-integration task |
| Hot reload (optional) | `just dev` | Direct HTTP on host Uvicorn/Streamlit after Docker-first setup |
| Containerized watch (advanced) | Manual Compose Watch | Core containers with source sync and reload for Compose debugging |
| Monitoring | `just dev-up-monitoring` | Opt-in Prometheus, Grafana, Loki/Promtail, Tempo, Alertmanager, Mailpit |

Use `just --list` for the current core workflow commands. Real AWS MVP delivery is **Decision**
evidence. Its application workload is versioned here and its platform bootstrap is handled by the sibling infra
[deployment guide](https://github.com/ivanprytula/api-observatory-infra/blob/main/docs/deployment/deployment-guide.md);
it is not a local environment profile.

## What You Don't Need

To contribute to the application, you do not need Terraform, Ansible, cloud CLIs, Kubernetes tools,
production TLS certificates, or real notification providers (Slack, email, webhooks). Install them
only for a task that owns that boundary, following the sibling infrastructure repository's
[README](https://github.com/ivanprytula/api-observatory-infra/blob/main/README.md).

## Optional Labs

Labs are deliberately outside the root command surface. Invoke them through `just/labs.just`; they
are disposable exercises, not alternate MVP runtimes, and they never start the Compose application
stack implicitly.

| Lab | Entry point | Boundary |
| --- | --- | --- |
| AWS emulator | `just --justfile just/labs.just lab-aws-up` | Starts only the disposable AWS API emulator; use `lab-aws-verify` and `lab-aws-down` for health and cleanup. This is not `aws-dev` parity or deployment evidence |
| Kubernetes | `just --justfile just/labs.just lab-k8s-up` | Builds and publishes one ingestor, one dashboard, and disposable PostgreSQL to k3d; tear down with `lab-k8s-down` |
| HTTPS ingress | `TLS_VERIFY=false just --justfile just/labs.just lab-ingress-smoke` | Checks an already-started local ingress |
| Load | `BEARER_TOKEN="$(just smoke-token)" just --justfile just/labs.just lab-load` | Bounded authenticated observation workload against an already-ready core stack |
| Chaos | `just --justfile just/labs.just lab-chaos` | Stops/restarts the local PostgreSQL container; use a disposable core stack |

## HTTP and HTTPS Split

Use Docker-first HTTP for onboarding, day-to-day editing, local API debugging, and focused tests:
`just dev-up` serves the ingestor at `http://127.0.0.1:8000` and the dashboard at
`http://127.0.0.1:8501`. After that path works, `just dev` is an optional host-process hot-reload
mode with the same `.env` feature flags. It starts PostgreSQL only by default; run the explicit
`dev-up-cache` or `dev-up-broker` recipe before using those integrations. Because `just dev` runs the
host servers in the foreground, use two terminals: keep `just dev` running in terminal 1, then run
migrations and tests from terminal 2 once `/readyz` returns `200`.

### Manual Compose Watch

For Compose-specific debugging (container reload, image rebuild, service networking), see the
[Compose Watch documentation](https://docs.docker.com/compose/how-tos/watch/). The project's
`just --justfile just/labs.just` recipes cover the same boundary without maintaining a local copy
of generic Compose syntax. Do not run the watcher alongside another local stack.

Use HTTPS when proving the public boundary: run
`just dev-up-ingress-setup` to install developer-trusted certificates, then start the `ingress` profile. The Nginx edge redirects port 80
to HTTPS, terminates TLS, and proxies the public API under `/api/`.

```bash
# Edit .env and set API_OBS_LOCAL_HTTPS=true before continuing.
just dev-up-ingress-setup
docker compose --profile ingress up -d --build
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

Cloud secret delivery is infrastructure-owned; the application only consumes environment variables
declared by the [deployment contract](../07-deployment/app-repo-contract.md).

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

Start with `just dev-up`; add only the profile needed by the task. Stop services without deleting data
with `docker compose stop`, or remove containers and the network with `docker compose down`. Never add
`--volumes` unless deleting local databases is intentional.

`just db-reset --confirm DELETE` is disposable-demo tooling. It removes and recreates the ingestor
PostgreSQL container and its local named volume, then starts only the core stack; Redis, Redpanda,
and the separate inference database remain opt-in and untouched. Stop using it once you have
registered real observations, real API URLs, or any other data you want to keep. For that data,
stop/start containers without resetting volumes. `db-reset` waits for the recreated core services;
then run `just db-migrate` and `just db-auto-init` when you need demo data.
Before any destructive database operation, create and verify a manual backup with
`just db-backup`; do not proceed until the dump is known to be usable.

Compose startup waits for declared service healthchecks; migrations and demo seeding remain explicit.
For inference work use:

```bash
just dev-up-inference
just db-migrate
just db-inference-migrate
```

| Capability | `.env` setting | Start command |
| --- | --- | --- |
| Redis integration | `API_OBS_CACHE_ENABLED=true` | Set the flag first, then `just dev-up-cache` |
| Broker integration | `API_OBS_BROKER_ENABLED=true` | Set the flag first, then `just dev-up-broker` |
| OpenTelemetry | `API_OBS_OTEL_ENABLED=true` | Restart `ingestor`, then run `just dev-up-monitoring` |
| HTTPS ingress | `API_OBS_LOCAL_HTTPS=true` | `just dev-up-ingress-setup` then `docker compose --profile ingress up -d --build` |

After changing a cache, broker, or telemetry flag, restart the ingestor so it receives the new
configuration. The broker carries general application events and the opt-in notification delivery
consumer. Direct notification delivery remains the default; the
[senior walkthrough](../05-development/dev-workflows.md#senior-extended-dependencies-and-failure-boundaries)
owns the explicit consumer startup path.

OpenTelemetry is disabled by default. To collect local traces, enable it, restart the ingestor, and
start monitoring:

```bash
docker compose restart ingestor
just dev-up-monitoring
```

Starting the monitoring UI alone
does not enable tracing in the application.

Cloud-emulator and Kubernetes exercises stay separate from the local application workflow. Use the
[optional labs](#optional-labs) commands only when their provider or orchestration boundary is the
subject of the exercise.

### Terraform Sandbox Commands

Use Terraform directly from the explicit local sandbox directory so the planned action remains
visible. For example:

```bash
cd infra/terraform/environments/aws-sandbox
terraform init
terraform validate
terraform plan
```

These directories are local learning environments. Real AWS MVP provisioning, apply, rollback,
and teardown remain infra-owned and require the separately approved delivery gate.

## Optional Local Capabilities

- Image/dependency scanning is owned by pre-commit and [CI workflows](../../.github/workflows/).
- Performance and fault work starts from the
  [performance/failure worksheet](../05-development/performance-and-failure-lab.md), which links the
  maintained scripts.

Production frontend replacements, ECS on Fargate, EKS, and additional IaaS providers are not active
setup modes. The AWS learning order and production adoption triggers live in the
[roadmap](../03-planning/mvp-roadmap.md).

## Verification and Troubleshooting

Use `just doctor`, service health/readiness endpoints, and the focused test recipes in the
[`Justfile`](../../Justfile). If startup fails, inspect Compose state and logs first:

```bash
docker compose ps
docker compose logs --tail=100 <service>
```

Then check migrations and the owning settings module rather than copying command sequences into this
guide.

For the development loop and proof selection, continue with
[development workflows](../05-development/dev-workflows.md).

## FAQ

### Docker daemon not running

Run `just doctor` first. It checks the daemon and Compose path. If Docker Desktop is installed but the daemon is stopped, start it and wait for `docker info` to succeed.

### Port conflicts

`just dev-up` uses `8000` (ingestor), `8501` (dashboard), `5432` (ingestor PostgreSQL), and `5433` (inference PostgreSQL). Stop the conflicting process or change the port in `.env` before restarting.

### `.env` generation

Never edit `.env` manually. Copy `.env.example`, then run `just generate-secrets` to create a local `.env` with user-only permissions (`0600`).

### testcontainers vs. local stack

`just test-integration` and other testcontainer-based recipes provision their own temporary PostgreSQL inside Docker. Do not run `just dev-up` first; the tests manage their own lifecycle.

### Migrations not applied

`just dev-up` returns only after services are healthy, but migrations are explicit. Run `just db-migrate` (and `just db-inference-migrate` for inference) after startup.

### MCP not starting

MCP is a local stdio process, not a Compose service. Follow the [MCP service README](../../services/mcp/README.md) for its one-time service-account setup and launch command.
