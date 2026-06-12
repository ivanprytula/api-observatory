# api-observatory

Async FastAPI service for API reliability monitoring, contract drift detection, scorecard reporting, and LangGraph-powered observation enrichment.

**MVP status**: Commits 1-12 complete. All core features shippable.

## Quick Start

```bash
cp .env.example .env
just up       # db, cache, broker, ingestor
just migrate
```

API docs: <http://localhost:8000/docs>

Full setup sequence: [docs/02-first-time-setup.md](docs/02-first-time-setup.md)
All commands: [docs/dev/commands.md](docs/dev/commands.md)

## Stack

| Service | Port | Role |
|---------|-----:|------|
| ingestor | 8000 | FastAPI — probes, scorecards, drift detection, agent enrichment |
| db | 5432 | PostgreSQL 17 — primary persistence, PERCENTILE_CONT scorecards, RLS |
| cache | 6379 | Cache (scorecard TTL), pub/sub (WebSocket fan-out), rate-limit backend |
| broker | 9092/8082 | Kafka-compatible broker — drift events, async processing, DLQ |

See [docs/04-architecture-overview.md](docs/04-architecture-overview.md) for the full flow diagram.

## Read Next

- [docs/README.md](docs/README.md) — Full docs index and track navigation
- [docs/user/overview.md](docs/user/overview.md) — User-facing guide (purpose, functionality)
- [docs/dev/commands.md](docs/dev/commands.md) — All CLI commands
- [docs/04-architecture-overview.md](docs/04-architecture-overview.md) — Visual flow diagram
- [docs/tech-map.md](docs/tech-map.md) — Interview topic → exact file:function map
- [docs/deployment/aws-ecs.md](docs/deployment/aws-ecs.md) — ECS deployment sequence
