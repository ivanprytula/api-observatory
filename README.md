# api-observatory

Async FastAPI service for API reliability monitoring, contract drift detection, scorecard reporting, and LangGraph-powered observation enrichment.

**MVP status**: Core features complete. CI/CD targets Azure free tier (ACR + B1s VM). Local dev uses floci-az emulator.

## Quick Start

```bash
cp .env.example .env
just up       # db, cache, broker, ingestor
just migrate
```

API docs: <http://localhost:8000/docs>

See the "First-Time Setup" guide for the full setup sequence.
See the "Commands Reference" for the CLI catalog.

## Stack

| Service | Port | Role |
|---------|-----:|------|
| ingestor | 8000 | FastAPI — probes, scorecards, drift detection, agent enrichment |
| db | 5432 | PostgreSQL 17 — primary persistence, PERCENTILE_CONT scorecards, RLS |
| cache | 6379 | Cache (scorecard TTL), pub/sub (WebSocket fan-out), rate-limit backend |
| broker | 9092/8082 | Kafka-compatible broker — drift events, async processing, DLQ |

See the "Architecture Overview" for the full flow diagram.

## Documentation Map

| Directory | What you'll find |
|-----------|-----------------|
| [01-intro/](docs/01-intro/) | Project overview, domain model, learning paths, environment matrix |
| [02-architecture/](docs/02-architecture/) | Architecture overview, ADRs, system design, design decisions |
| [03-planning/](docs/03-planning/) | MVP scope, audit gaps, prompting checklist |
| [04-setup/](docs/04-setup/) | Environment bootstrap — system setup, first-time setup, local HTTPS |
| [05-development/](docs/05-development/) | Daily dev workflow, commands reference, Bruno collections, testing |
| [06-ci-cd/](docs/06-ci-cd/) | CI/CD workflow reference, prebuilt images, security hardening |
| [07-deployment/](docs/07-deployment/) | Cloud deployment guides, security checklist, runbooks |
| [08-operations/](docs/08-operations/) | Observability, webhooks, incident runbooks |
| [09-user-guides/](docs/09-user-guides/) | Dashboard, scorecards, WebSocket, Streamlit |
| [services/ingestor/](services/ingestor/) | FastAPI service source — routes, schemas, repos, agent, tests |
| [tests/](tests/) | Test suite — unit, integration, e2e, shared fixtures |
| [libs/](libs/) | Shared Python libraries — contracts, resilience, platform |
| [infra/](infra/) | Local dev infra — Docker Compose, sandbox TF, k3d, Ansible (local) |
| [api-observatory-infra](https://github.com/ivanprytula/api-observatory-infra) | Cloud infrastructure — Terraform (cloud envs), K8s, Helm, prod monitoring |
| [scripts/](scripts/) | Shell scripts — setup, testing, daily dev, deployment |
| [.github/hooks/](.github/hooks/) | Pre-commit hooks — secrets scanner, tool guardian, governance audit |

## Read Next

- User Guide — purpose, functionality
- Commands Reference — CLI catalog
- Architecture Overview — visual flow diagram
- Deployment Guide — cloud deployment sequence
