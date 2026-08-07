# ingestor

Write-side CQRS service. Ingests pipeline observations into PostgreSQL via a REST API,
manages scraping jobs, and publishes events to Redpanda.

## Quick Start

The repository [Setup Guide](../../docs/04-setup/setup-guide.md) owns prerequisites, local
configuration, and core/extended stack choices. From the repository root, start the canonical core
stack with:

```bash
just dev-up
just db-migrate
```

For Redis, Redpanda, inference, or host-process hot reload, follow the corresponding explicit path
in the setup guide rather than starting Compose services directly.

Check the ingestor independently with:

```bash
curl --fail http://127.0.0.1:8000/readyz
```

## Ports

| Service | Port | Environment |
| --- | --- | --- |
| FastAPI API | `8000` | Local core and extended stacks |

## Key Environment Variables

| Variable        | Default                    | Notes                                           |
| --------------- | -------------------------- | ----------------------------------------------- |
| `DATABASE_URL`  | `postgresql+asyncpg://...` | Must include `+asyncpg` dialect prefix          |
| `DB_ECHO`       | `false`                    | Set `true` to log all SQL                       |
| `LOG_LEVEL`     | `INFO`                     | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `CACHE_URL`     | `redis://localhost:6379/0` | Cache URL; Compose injects `redis://cache:6379/0` |
| `INFERENCE_URL` | `http://localhost:8001`    | Upstream vector-search service; Compose injects `http://inference:8001` |

## Architecture

```text
FastAPI routes (routers/)
  └─ Pydantic v2 validation (api_schemas/)
  └─ DbDep = Annotated[AsyncSession, Depends(get_db)]
       └─ Repository layer (repositories/) — pure async functions
            └─ AsyncSessionLocal (database.py)
                 └─ asyncpg → PostgreSQL 17
```

## API Endpoints

| Method | Path                        | Description                      |
| ------ | --------------------------- | -------------------------------- |
| GET    | `/readyz`                   | Readiness probe                  |
| GET    | `/health`                   | Liveness probe                   |
| GET    | `/api/v1/observations`           | List observations with pagination     |
| POST   | `/api/v1/observations`           | Create an observation                  |
| GET    | `/api/v1/observations/{id}`      | Retrieve an observation                |
| PUT    | `/api/v1/observations/{id}`      | Update an observation                  |
| DELETE | `/api/v1/observations/{id}`      | Delete an observation                  |
| POST   | `/api/v1/observations/batch`     | Bulk create up to 1 000 observations  |
| POST   | `/api/v1/webhooks/{source}` | Receive an inbound webhook event |

## Running Tests

```bash
# From the repository root. Unit tests are isolated; Docker enables temporary
# PostgreSQL/Redis testcontainers for dependency-specific integration tests.
# Use the running core stack for smoke, API, or E2E checks instead.
uv run pytest services/ingestor/tests -q
```

## Further Reading

- [Setup Guide](../../docs/04-setup/setup-guide.md)
- [Development Workflows](../../docs/05-development/dev-workflows.md)
- [Application Architecture](../../docs/02-architecture/application-architecture.md)
