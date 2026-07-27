# Setup Guide

Local Docker Compose is the canonical runtime. The [`Justfile`](../../Justfile) owns command syntax;
this guide explains which mode to choose, what it proves, and where configuration lives.

## Prerequisites

Required tools are Docker with Compose, Python 3.14, `uv`, `just`, Git, and `curl`. PostgreSQL/Redis
clients, k6, Bruno, Terraform, cloud CLIs, kubectl, Helm, and k3d/k3s are optional for their
corresponding workflows. Run `just doctor` for the maintained environment check.

Never read or commit a local `.env`. Copy the public, non-secret
[`.env.example`](../../.env.example), then generate local credentials privately.

## Quick Start

```bash
cp .env.example .env
just generate-secrets
# First HTTPS ingress run on this workstation:
bash scripts/setup/02-setup-local-https.sh
just up
```

`just generate-secrets` creates or rotates the local prod-like passwords and tokens in `.env` without
printing them. The [`Justfile`](../../Justfile) owns the remaining executable workflows.

`just up` is the HTTPS ingress-parity workflow. After local certificates are installed, use
`https://127.0.0.1/api/docs` for the OpenAPI UI and `https://127.0.0.1` for the dashboard. Direct
HTTP ports (`http://127.0.0.1:8000` and `http://127.0.0.1:8501`) remain available for debugging.

## Supported Local Modes

| Mode | Entry point | Use |
| --- | --- | --- |
| Docker-first | `just up` | HTTPS ingress parity through Nginx; requires local certificates |
| Hot reload | `just dev` | Direct HTTP on host Uvicorn/Streamlit for the fast inner loop |
| Monitoring | `just up-monitoring` or `just up-all` | Opt-in Prometheus, Grafana, Loki/Promtail, Tempo, Alertmanager, Mailpit |
| Cloud emulator | `CLOUD=<aws|azure|gcp> just sandbox-up` | Zero-cost provider-shaped API/IaC exercises, not real cloud behavior |
| Local Kubernetes | `just k3s-up` | Orchestration lab; Compose remains canonical |

The [`Justfile`](../../Justfile) documents companion stop, status, test, and teardown recipes. Real
AWS Stage 0 is **Decision** evidence and is handled by the sibling infra
[deployment guide](https://github.com/ivanprytula/api-observatory-infra/blob/main/docs/deployment/deployment-guide.md),
not by a local environment profile.

## HTTP and HTTPS Split

Use direct HTTP for day-to-day editing, local API debugging, and focused tests: `just dev` serves
the ingestor at `http://127.0.0.1:8000` and the dashboard at `http://127.0.0.1:8501`. This keeps
the inner loop independent of local certificate tooling.

Use HTTPS when proving the public boundary: install developer-trusted certificates with
[`scripts/setup/02-setup-local-https.sh`](../../scripts/setup/02-setup-local-https.sh), then run
`just up`. The Nginx edge redirects port 80 to HTTPS, terminates TLS, and proxies the public API
under `/api/`. Exercise this path for cookies, redirects, proxy headers, mixed-content/CSP checks,
WebSockets, and pre-deployment smoke tests.

Production always terminates TLS at its public ingress or load balancer. Internal container traffic
uses private Compose networking; adding end-to-end TLS or mTLS requires an explicit trust-boundary
requirement.

## Configuration Ownership

- [`.env.example`](../../.env.example) contains public core-development settings only.
- `.env` is ignored and holds the generated local credentials. The application receives all
  configuration through environment variables; the file is only a local developer convenience.
- [`services/ingestor/config.py`](../../services/ingestor/config.py) owns ingestor defaults,
  validation, feature flags, and secret classification.
- [`services/inference/config.py`](../../services/inference/config.py) and
  [`services/mcp/config.py`](../../services/mcp/config.py) own their service-specific settings.
- [`docker-compose.yml`](../../docker-compose.yml) owns service wiring, ports, profiles, and
  container-to-container addresses.

Core operation requires PostgreSQL and authentication configuration. Redis, Redpanda, telemetry,
notifications, background workers, external AI providers, and demo routes remain optional or
feature-gated. Host processes use `127.0.0.1`; containers use Compose DNS names such as `db`,
`cache`, and `broker`.

Local secrets may come from the ignored `.env`. Cloud secret delivery is infrastructure-owned; the
application only consumes environment variables declared by the
[deployment contract](../07-deployment/app-repo-contract.md).

## Runtime Shapes

| Setup | Containers | What it proves | Operational cost |
| --- | --- | --- | --- |
| Core architecture | Ingestor, PostgreSQL | API monitoring, persistence, scheduling, and incident behavior | Lowest |
| `just up` | Core demo plus Redis, Redpanda, dashboard, and edge | Integration, user interface, HTTPS path, cache, and event behavior | Moderate |
| Base Compose | `docker compose up` additionally starts inference and its dedicated PostgreSQL database | Semantic search and RAG path | Higher |
| `just up-all` | `just up` plus Prometheus, Grafana, Loki, Promtail, Tempo, Alertmanager, and Mailpit | Focused local observability exercises | Highest |

Choose the smallest shape that proves the behavior you are working on. Cache, broker, telemetry,
AI, cloud emulators, backups, and notifications are opt-in capabilities, not baseline requirements.

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
[`Justfile`](../../Justfile). If startup fails, inspect the Compose service state and logs, then
check migrations and the owning settings module rather than copying command sequences into this
guide.

For the development loop and proof selection, continue with
[development workflows](../05-development/dev-workflows.md).
