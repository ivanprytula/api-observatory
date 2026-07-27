# Setup Guide

Local Docker Compose is the canonical runtime. The [`Justfile`](../../Justfile) owns command syntax;
this guide explains which mode to choose, what it proves, and where configuration lives.

## Prerequisites

Required tools are Docker with Compose, Python 3.14, `uv`, `just`, Git, and `curl`. PostgreSQL/Redis
clients, k6, Bruno, Terraform, cloud CLIs, kubectl, Helm, and k3d/k3s are optional for their
corresponding workflows. Run `just doctor` for the maintained environment check.

Never read or commit a local `.env`. Copy the placeholder-only [`.env.example`](../../.env.example)
and supply local values privately.

## Quick Start

Copy [`.env.example`](../../.env.example) to a private local `.env`, then use the
[`Justfile`](../../Justfile) targets `up`, `migrate`, and `init`. Those files own the executable
sequence.

The API is available at `http://127.0.0.1:8000`, its OpenAPI UI at `/docs`, and Streamlit at
`http://127.0.0.1:8501`. Verify `/health` before using the demo.

## Supported Local Modes

| Mode | Entry point | Use |
| --- | --- | --- |
| Docker-first | `just up` | Canonical application/data-plane runtime and integration target |
| Hot reload | `just dev` | Container dependencies with host Uvicorn for debugging |
| Monitoring | `just up-monitoring` or `just up-all` | Opt-in Prometheus, Grafana, Loki/Promtail, Tempo, Alertmanager, Mailpit |
| Cloud emulator | `CLOUD=<aws|azure|gcp> just sandbox-up` | Zero-cost provider-shaped API/IaC exercises, not real cloud behavior |
| Local Kubernetes | `just k3s-up` | Orchestration lab; Compose remains canonical |

The [`Justfile`](../../Justfile) documents companion stop, status, test, and teardown recipes. Real
AWS Stage 0 is **Decision** evidence and is handled by the sibling infra
[deployment guide](https://github.com/ivanprytula/api-observatory-infra/blob/main/docs/deployment/deployment-guide.md),
not by a local environment profile.

## Configuration Ownership

- [`.env.example`](../../.env.example) lists safe placeholder names for local use.
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

## Optional Local Capabilities

- HTTPS/edge parity is owned by the Compose `ingress` profile and
  [`scripts/setup/02-setup-local-https.sh`](../../scripts/setup/02-setup-local-https.sh).
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
