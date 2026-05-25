# api-observatory

Async FastAPI service for API reliability monitoring, contract drift detection, scorecard reporting, and LangGraph-powered record enrichment.

**MVP status**: Commits 1-12 complete. All core features shippable.

## Quick Start

```bash
cp .env.example .env
# Set REDIS_ENABLED=true and KAFKA_ENABLED=true for full feature set
docker compose up -d --build
curl -s http://localhost:8000/docs
```

## Stack

| Service | Port | Why it's here |
|---------|-----:|---------------|
| ingestor | 8000 | FastAPI — API probes, scorecards, drift detection, agent enrichment |
| db | 5432 | PostgreSQL 17 — primary persistence, PERCENTILE_CONT scorecards, RLS |
| redis | 6379 | Cache (scorecard TTL), pub/sub (WebSocket fan-out), rate-limit backend |
| redpanda | 9092/8082 | Kafka-compatible broker — drift events, async processing, DLQ |

> See [docs/04-architecture-overview.md](docs/04-architecture-overview.md) for the full Mermaid flow diagram
> and per-service justification.

## Enable Redis and Redpanda

Both are **opt-in** so unit tests run without infrastructure:

```bash
# In .env (or export before docker compose up):
REDIS_ENABLED=true
REDIS_URL=redis://redis:6379/0

KAFKA_ENABLED=true
KAFKA_BROKER_URL=redpanda:29092   # inside Docker network
# KAFKA_BROKER_URL=localhost:9092 # from host machine
```

The `docker-compose.yml` sets these automatically for the ingestor container.

## Streamlit Dashboard

```bash
uv run streamlit run streamlit_app.py
# → http://localhost:8501
# Panels: Source Health, Drift Events, Live Stream (WebSocket), Agent Enrichment, Service Health
```

## Test the API

```bash
docker compose up -d
just api-test
# runs: cd bruno && bru run . -r --env local
```

## Read Next

- [docs/04-architecture-overview.md](docs/04-architecture-overview.md) — Visual flow diagram, service justifications
- [docs/tech-map.md](docs/tech-map.md) — Interview topic → exact file:function map
- [docs/learning-paths.md](docs/learning-paths.md) — Four learning tracks (backend, distributed, devops, agent)
- [docs/dev/bruno-collections.md](docs/dev/bruno-collections.md) — API testing with Bruno CLI
- [docs/README.md](docs/README.md) — Full docs index
