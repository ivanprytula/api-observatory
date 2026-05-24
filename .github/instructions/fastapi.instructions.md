---
description: "Use when writing, adding, or reviewing FastAPI routes, dependencies, lifespan, error handling, or app configuration. Covers official FastAPI best practices: async routes, Annotated dependencies, lifespan context, APIRouter, HTTPException, status constants, and Pydantic v2 schema conventions."
applyTo: ["app/**/*.py", "tests/**/*.py"]
---

# FastAPI Best Practices

## Route Functions — Always `async def`

All route handlers must be `async def`. Never use sync `def` in routes — it blocks the event loop:

```python
# CORRECT
@app.get("/api/v1/records/{record_id}", response_model=RecordResponse)
async def get_record_endpoint(record_id: int, db: DbDep) -> RecordResponse:
    ...

# WRONG — blocks event loop, kills concurrency
@app.get("/api/v1/records/{record_id}")
def get_record_endpoint(record_id: int):
    ...
```

## Response Models and Status Codes

Always specify `response_model` and `status_code` on non-200 responses. Use `status.HTTP_*` constants — never raw integers:

```python
from fastapi import status

# CORRECT
@app.post(
    "/api/v1/records",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["records"],
)

# WRONG — magic numbers, missing model
@app.post("/api/v1/records", status_code=201)
```

Add `tags` to every route for OpenAPI grouping and `/docs` navigation.

## Dependency Injection — `Annotated` Style

Use `Annotated[Type, Depends(...)]` for all dependencies. Define type aliases for repeated deps:

```python
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession

# CORRECT — Python 3.12+ type alias
type DbDep = Annotated[AsyncSession, Depends(get_db)]

@app.get("/api/v1/records")
async def list_records(db: DbDep) -> list[RecordResponse]:
    ...

# WRONG — old inline style
@app.get("/api/v1/records")
async def list_records(db: AsyncSession = Depends(get_db)):
    ...
```

Use `yield` dependencies with `try/finally` for resources that need cleanup:

```python
async def get_db() -> AsyncGenerator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session  # explicit close on teardown
```

## Lifespan — Never `@app.on_event`

Use the `lifespan` context manager. `@app.on_event("startup")` is deprecated since FastAPI 0.93:

```python
from contextlib import asynccontextmanager

# CORRECT
@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # shutdown
    await engine.dispose()

app = FastAPI(lifespan=lifespan)

# WRONG — deprecated
@app.on_event("startup")
async def startup():
    ...
```

## Error Handling — `HTTPException`

Raise `HTTPException` with explicit `status_code` and `detail`. Use `status.HTTP_*` constants:

```python
from fastapi import HTTPException, status

# CORRECT
record = await get_record(db, record_id)
if record is None:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Record not found",
    )

# WRONG — raw integer
raise HTTPException(status_code=404, detail="Not found")
```

For domain-level error types, register a custom exception handler at the app level rather than catching exceptions in individual routes:

```python
@app.exception_handler(RecordNotFoundError)
async def record_not_found_handler(request: Request, exc: RecordNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})
```

## Query Parameter Validation — `Annotated + Query`

Validate query parameters inline using `Annotated[T, Query(...)]`:

```python
from fastapi import Query

# CORRECT
@app.get("/api/v1/records")
async def list_records(
    db: DbDep,
    skip: Annotated[int, Query(ge=0, description="Offset")] = 0,
    limit: Annotated[int, Query(ge=1, le=1000, description="Page size")] = 100,
    source: str | None = None,
) -> RecordListResponse:
    ...

# WRONG — no constraints
async def list_records(db: DbDep, skip: int = 0, limit: int = 100):
    ...
```

## Router Organization — `APIRouter`

Use `APIRouter` for feature modules. Mount routers with a shared prefix and tags:

```python
# app/routers/records.py
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/records", tags=["records"])

@router.get("/", response_model=RecordListResponse)
async def list_records(...):
    ...

# app/main.py
from app.routers import records

app.include_router(records.router)
```

Never put all routes directly on `app` once there are more than one resource. Use `APIRouter` from the first endpoint of each resource.

## App Configuration

Always provide `title`, `version`, and `description`. Read from `pydantic-settings`:

```python
from app.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="...",
    lifespan=lifespan,
)
```

## Return Type Hints

All route functions must have explicit return type annotations — this enables static analysis and avoids relying solely on `response_model` for type safety:

```python
# CORRECT
async def get_record_endpoint(record_id: int, db: DbDep) -> RecordResponse:

# WRONG
async def get_record_endpoint(record_id: int, db: DbDep):
```

## Pydantic v2 Schema Conventions

- Separate request and response schemas — never reuse the same model for both
- Add `model_config = {"from_attributes": True}` on all response schemas that map to ORM models
- Validate inputs at the schema level with `field_validator` — never in route bodies
- Use `Field(...)` for constraints, not inline `Query`/`Body` on schema fields

```python
class RecordResponse(BaseModel):
    id: int
    source: str
    model_config = {"from_attributes": True}  # required for ORM → schema mapping
```

## Correlation IDs

Every mutating endpoint (`POST`, `PUT`, `PATCH`, `DELETE`) must generate and log a `cid` (correlation ID) for tracing:

```python
import uuid

cid = str(uuid.uuid4())
logger.info("record_create", extra={"source": request.source, "cid": cid})
record = await create_record(db, request)
logger.info("record_created", extra={"id": record.id, "cid": cid})
```
