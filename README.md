# api-observatory

Async FastAPI service for API reliability monitoring, contract drift detection, and scorecard reporting.

## Quick Start

```bash
cp .env.example .env
docker compose up -d --build
curl -s http://localhost:8000/docs
```

## What's Running

| Service | Port | Purpose |
|---|---:|---|
| ingestor | 8000 | FastAPI API, probes, scorecards, drift endpoints |
| db | 5432 | PostgreSQL 17 with optional extension bootstrap |
| redis | 6379 | Cache/pubsub and rate-limit backend |
| redpanda | 9092 / 8082 | Kafka-compatible event broker |

## Read Next

- [docs/tech-map.md](docs/tech-map.md)
- [docs/learning-paths.md](docs/learning-paths.md)
- [docs/dev/mvp-mvp-plus-usage.md](docs/dev/mvp-mvp-plus-usage.md)
- [docs/README.md](docs/README.md)
