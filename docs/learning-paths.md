# Learning Paths

## Backend Interview Prep

1. Run the stack and inspect docs endpoint.
2. Walk through request flow in [services/ingestor/main.py](services/ingestor/main.py) and [services/ingestor/routers](services/ingestor/routers).
3. Review persistence and async DB patterns in [services/ingestor/models.py](services/ingestor/models.py) and [services/ingestor/repositories](services/ingestor/repositories).
4. Practice explaining trade-offs from [docs/tech-map.md](docs/tech-map.md).

## Distributed Systems Track

1. Study event and scheduling flow in [services/ingestor/jobs.py](services/ingestor/jobs.py) and [services/ingestor/jobs_registry.py](services/ingestor/jobs_registry.py).
2. Review reliability controls in [libs/platform/circuit_breaker.py](libs/platform/circuit_breaker.py) and [services/ingestor/rate_limiting.py](services/ingestor/rate_limiting.py).
3. Analyze contract drift and scoring paths in [services/ingestor/routers/contract_drift.py](services/ingestor/routers/contract_drift.py) and [services/ingestor/routers/scorecards.py](services/ingestor/routers/scorecards.py).

## DevOps and Cloud Track

1. Start with local runtime orchestration in [docker-compose.yml](docker-compose.yml).
2. Review image/runtime hardening in [Dockerfile](Dockerfile) and [infra/database/Dockerfile](infra/database/Dockerfile).
3. Study infrastructure modules in [infra/terraform](infra/terraform).
4. Read deployment workflow in [docs/floci-aws-deployment-workflow.md](docs/floci-aws-deployment-workflow.md).
