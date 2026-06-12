# ingestor

Write-side CQRS service. Ingests pipeline observations into PostgreSQL via a REST API,
manages scraping jobs, and publishes events to Redpanda.

## Quick Start

### Prerequisites

- Docker, Docker Compose
- Python 3.14+ (for running tests locally)

### Spin Up

```bash
docker compose up ingestor db cache
```

### Check Health

```bash
curl http://localhost:8000/readyz
```

## Ports

| Service              | Port   | Environment |
| -------------------- | ------ | ----------- |
| FastAPI (API)        | `8000` | All         |
| Streamlit (Dashboard)| `8501` | Docker (`just up`) |

## Key Environment Variables

| Variable        | Default                    | Notes                                           |
| --------------- | -------------------------- | ----------------------------------------------- |
| `DATABASE_URL`  | `postgresql+asyncpg://...` | Must include `+asyncpg` dialect prefix          |
| `DB_ECHO`       | `false`                    | Set `true` to log all SQL                       |
| `LOG_LEVEL`     | `INFO`                     | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `CACHE_URL`     | `redis://cache:6379/0`     | Used for rate limiting and caching              |
| `INFERENCE_URL` | `http://inference:8001`    | Upstream vector search service                  |

## Architecture

```text
FastAPI routes (routers/)
  └─ Pydantic v2 validation (schemas.py)
  └─ DbDep = Annotated[AsyncSession, Depends(get_db)]
       └─ CRUD layer (crud.py)  — pure async functions
            └─ AsyncSessionLocal (database.py)
                 └─ asyncpg → PostgreSQL 17
```

## API Endpoints

| Method | Path                        | Description                      |
| ------ | --------------------------- | -------------------------------- |
| GET    | `/readyz`                   | Readiness probe                  |
| GET    | `/healthz`                  | Liveness probe                   |
| GET    | `/api/v1/observations`           | List observations with pagination     |
| POST   | `/api/v1/observations`           | Create an observation                  |
| GET    | `/api/v1/observations/{id}`      | Retrieve an observation                |
| PUT    | `/api/v1/observations/{id}`      | Update an observation                  |
| DELETE | `/api/v1/observations/{id}`      | Delete an observation                  |
| POST   | `/api/v1/observations/batch`     | Bulk create up to 1 000 observations  |
| POST   | `/api/v1/webhooks/{source}` | Receive an inbound webhook event |

## Running Tests

```bash
# From repo root — no PostgreSQL needed (aiosqlite in-memory)
uv run pytest services/ingestor/tests/ -v
```

## Cleanup

```bash
docker compose down ingestor
```

## Further Reading

- [Architecture Overview](../../docs/04-architecture-overview.md)
- [Backend Concepts and Patterns](../../docs/09-backend-concepts-and-patterns.md)
