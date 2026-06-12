# Tech Map

Interview topics mapped to concrete implementation points.

| Topic | Where in code |
|---|---|
| Async Python | [services/ingestor/fetch.py](services/ingestor/fetch.py), [services/ingestor/database.py](services/ingestor/database.py) |
| SQLAlchemy 2.0 async | [services/ingestor/models.py](services/ingestor/models.py), [services/ingestor/repositories](services/ingestor/repositories) |
| APScheduler jobs | [services/ingestor/jobs.py](services/ingestor/jobs.py), [services/ingestor/jobs_registry.py](services/ingestor/jobs_registry.py) |
| Cache cache + pub/sub | [services/ingestor/cache.py](services/ingestor/cache.py), [services/ingestor/rate_limiting.py](services/ingestor/rate_limiting.py), [services/ingestor/routers/ws.py](services/ingestor/routers/ws.py) |
| Circuit breaker | [libs/platform/circuit_breaker.py](libs/platform/circuit_breaker.py) |
| Multi-tenancy/RLS path | [services/ingestor/security](services/ingestor/security), [alembic/versions](alembic/versions) |
| Observability | [services/ingestor/metrics.py](services/ingestor/metrics.py), [services/ingestor/main.py](services/ingestor/main.py) |
| LangGraph HITL + SSE | [services/ingestor/agent/graph.py](services/ingestor/agent/graph.py), [services/ingestor/routers/agent.py](services/ingestor/routers/agent.py) |
| WebSocket realtime | [services/ingestor/routers/ws.py](services/ingestor/routers/ws.py) |
| Contract drift | [services/ingestor/routers/contract_drift.py](services/ingestor/routers/contract_drift.py), [services/ingestor/routers/scorecards.py](services/ingestor/routers/scorecards.py) |
| GitHub Actions CI/CD | [.github/workflows](.github/workflows) |
| Terraform ECS | [infra/terraform](infra/terraform) |
