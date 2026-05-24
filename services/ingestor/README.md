# ingestor

Write-side CQRS service. Ingests pipeline records into PostgreSQL via a REST API,
manages scraping jobs, and publishes events to Redpanda.

## Quick Start

### Prerequisites

- Docker, Docker Compose
- Python 3.14+ (for running tests locally)

### Spin Up

```bash
docker compose up ingestor db redis
```

### Check Health

```bash
curl http://localhost:8000/readyz
```

## Port

| Environment    | Port   |
| -------------- | ------ |
| Docker Compose | `8000` |
| Local dev      | `8000` |

## Key Environment Variables

| Variable        | Default                    | Notes                                           |
| --------------- | -------------------------- | ----------------------------------------------- |
| `DATABASE_URL`  | `postgresql+asyncpg://...` | Must include `+asyncpg` dialect prefix          |
| `DB_ECHO`       | `false`                    | Set `true` to log all SQL                       |
| `LOG_LEVEL`     | `INFO`                     | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `REDIS_URL`     | `redis://redis:6379/0`     | Used for rate limiting and caching              |
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
| GET    | `/api/v1/records`           | List records with pagination     |
| POST   | `/api/v1/records`           | Create a record                  |
| GET    | `/api/v1/records/{id}`      | Retrieve a record                |
| PUT    | `/api/v1/records/{id}`      | Update a record                  |
| DELETE | `/api/v1/records/{id}`      | Delete a record                  |
| POST   | `/api/v1/records/batch`     | Bulk create up to 1 000 records  |
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
