---
description: "Use when writing, adding, or reviewing CRUD functions. Covers async SQLAlchemy 2.0 patterns: session as first argument, single vs batch inserts, refresh semantics, select() DSL, pagination queries, and return type conventions."
applyTo: "app/crud.py"
---

# CRUD Function Conventions

## Function Signature

All CRUD functions must be `async def` with `AsyncSession` as the **first positional argument** and explicit return type:

```python
# CORRECT
async def get_record(session: AsyncSession, record_id: int) -> Record | None:
    return await session.get(Record, record_id)

async def create_record(session: AsyncSession, request: RecordRequest) -> Record:
    ...

# WRONG — session is not first, missing return type
async def create_record(request: RecordRequest, session: AsyncSession):
    ...
```

Always return ORM models (`Record`, `User`, etc.), never dicts or serialized JSON. Let Pydantic handle serialization at the API boundary.

## Single Insert — `session.add()` + `commit()` + `refresh()`

For single-record inserts, follow this three-step pattern:

```python
async def create_record(session: AsyncSession, request: RecordRequest) -> Record:
    record = Record(
        source=request.source,
        timestamp=request.timestamp,
        raw_data=request.data,
        tags=request.tags,
    )
    session.add(record)
    await session.commit()  # flush + persist to DB
    await session.refresh(record)  # reload from DB to get server defaults (id, created_at)
    return record
```

The `refresh()` step is **critical** — it hydrates server-generated fields like `id`, `created_at`, `updated_at`. Without it, these attributes are `None` until the session is garbage-collected.

## Batch Insert — `session.add_all()` + Single `commit()` + Loop `refresh()`

For bulk inserts, use `add_all()` for a single round-trip, then refresh all in a loop:

```python
async def create_records_batch(
    session: AsyncSession, requests: list[RecordRequest]
) -> list[Record]:
    """Bulk-insert — one round-trip to the database."""
    records = [
        Record(
            source=r.source,
            timestamp=r.timestamp,
            raw_data=r.data,
            tags=r.tags,
        )
        for r in requests
    ]
    session.add_all(records)
    await session.commit()
    # Refresh to hydrate server-default fields (id, created_at …)
    for record in records:
        await session.refresh(record)
    return records
```

Never call `commit()` inside the loop — always commit once, then refresh in the loop. This ensures atomicity and minimizes round-trips.

## Primary Key Lookup — `session.get()`

For fetching by primary key, use `session.get()` — it's the most efficient:

```python
# CORRECT
async def get_record(session: AsyncSession, record_id: int) -> Record | None:
    return await session.get(Record, record_id)

# WRONG — overly verbose
stmt = select(Record).where(Record.id == record_id)
return (await session.execute(stmt)).scalar_one_or_none()
```

`session.get()` returns `None` if not found — check before using, or catch `NoResultFound` if you expect one to exist.

## Queries — `select()` DSL (Never Raw SQL)

Use the `select()` function for all queries. Never use raw SQL strings:

```python
from sqlalchemy import func, select

# CORRECT — method chaining
stmt = select(Record).where(Record.source == "api.example.com").order_by(Record.id)
records = (await session.execute(stmt)).scalars().all()

# WRONG — raw SQL (NO!)
results = await session.execute("SELECT * FROM records WHERE source = ?", ("api.example.com",))
```

Chain methods: `.where()` for filtering, `.order_by()` for sorting, `.offset()` / `.limit()` for pagination.

## Aggregates — `func.*` From SQLAlchemy

For counts, sums, averages, use `sqlalchemy.func`:

```python
from sqlalchemy import func, select

# Count records with filtering
count_q = select(func.count()).select_from(Record).where(Record.source == "api.com")
total = (await session.execute(count_q)).scalar_one()

# Sum a numeric column
sum_q = select(func.sum(Record.value)).select_from(Record)
total_value = (await session.execute(sum_q)).scalar()  # may be None if no rows
```

Always use `.scalar_one()` for aggregates that must return exactly one value. Use `.scalar()` if the value may be `None`.

## Pagination — Separate Count + Data Queries

Build count and data queries separately, then apply the same WHERE clauses to both:

```python
async def get_records(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    source: str | None = None,
) -> tuple[list[Record], int]:
    # Build base queries
    count_q = select(func.count()).select_from(Record)
    data_q = select(Record).order_by(Record.id).offset(skip).limit(limit)

    # Apply same WHERE clause to both
    if source:
        count_q = count_q.where(Record.source == source)
        data_q = data_q.where(Record.source == source)

    # Execute both
    total = (await session.execute(count_q)).scalar_one()
    records = list((await session.execute(data_q)).scalars().all())

    return records, total
```

This pattern ensures the total count matches the filtered data set, and reuses filter logic (no duplication).

## Update — Fetch, Mutate, Commit, Refresh

For updates, fetch the record, mutate attributes, commit, then refresh to catch any triggers or computed fields:

```python
async def mark_processed(session: AsyncSession, record_id: int) -> Record | None:
    record = await session.get(Record, record_id)
    if record is None:
        return None
    record.processed = True
    await session.commit()
    await session.refresh(record)  # catch updated_at or any DB-generated values
    return record
```

If the record doesn't exist, return `None` early — let the route decide how to respond (404, etc.).

## Delete Pattern — Soft vs Hard

### Hard Delete (Immediate Removal)

For hard deletes, physically remove the row from the database:

```python
async def delete_record(session: AsyncSession, record_id: int) -> bool:
    record = await session.get(Record, record_id)
    if record is None:
        return False
    await session.delete(record)
    await session.commit()
    return True
```

Return `bool` to indicate success/not-found. Never raise exceptions — let the route decide.

### Soft Delete (Timestamp-Based Archival)

When adding a `deleted_at` column to the model, follow the **update pattern** instead:

```python
# Model definition (in app/models.py)
from datetime import UTC, datetime

class Record(Base):
    ...
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

# CRUD function
async def delete_record(session: AsyncSession, record_id: int) -> Record | None:
    record = await session.get(Record, record_id)
    if record is None:
        return None
    record.deleted_at = datetime.now(UTC).replace(tzinfo=None)
    await session.commit()
    await session.refresh(record)
    return record
```

Soft deletes return the **updated record** (not `bool`), so the caller can verify the timestamp was set. This aligns with the update pattern and enables audit trails.

### Hiding Soft-Deleted Records

When soft-deleted records exist, all queries must exclude them:

```python
async def get_records(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    source: str | None = None,
) -> tuple[list[Record], int]:
    # Always exclude soft-deleted records
    count_q = select(func.count()).select_from(Record).where(Record.deleted_at.is_(None))
    data_q = select(Record).where(Record.deleted_at.is_(None)).order_by(Record.id).offset(skip).limit(limit)

    if source:
        count_q = count_q.where(Record.source == source)
        data_q = data_q.where(Record.source == source)

    total = (await session.execute(count_q)).scalar_one()
    records = list((await session.execute(data_q)).scalars().all())

    return records, total
```

Add `.where(Model.deleted_at.is_(None))` to every query to hide soft-deleted records by default. Create a separate function if you need to query deleted records for audit/recovery.

## Avoid N+1 Queries

If you're loading a Record and then accessing a related entity (e.g., `record.user`), use `selectinload()` to eagerly fetch:

```python
from sqlalchemy.orm import selectinload

# CORRECT — one query with LEFT JOIN
stmt = select(Record).options(selectinload(Record.user)).where(Record.id == 1)

# WRONG — two queries: one for Record, then one for User when accessed
stmt = select(Record).where(Record.id == 1)
record = (await session.scalar_one(stmt))
_ = record.user  # N+1 — triggers another query
```

For this project (Week 1), all queries are single-table, so this is not yet a concern — but follow the pattern once relationships are added.

## Execution Methods

| Method | Use for | Returns |
|--------|---------|---------|
| `await session.execute(stmt)` | All queries | `CursorResult` — iterate via `.scalars()`, `.all()`, etc. |
| `await session.get(Model, pk)` | PK lookups | `Model \| None` directly |
| `await session.commit()` | Persist inserts/updates/deletes | `None` — side effect is persistence |
| `await session.refresh(record)` | Reload from DB after commit | `None` — mutates `record` in-place |
| `await session.delete(record)` | Hard delete | `None` — queues for deletion on next `commit()` |

## Parameterized Queries

All user input is parameterized automatically by SQLAlchemy's `select()` DSL. **Never use string formatting**:

```python
# CORRECT — SQL injection safe
source = request.source  # user input
stmt = select(Record).where(Record.source == source)

# WRONG — SQL injection risk (DO NOT DO)
stmt = f"SELECT * FROM records WHERE source = '{source}'"
```

## Return Types — Always Explicit

Every CRUD function must have an explicit return type, including empty returns:

```python
# CORRECT
async def get_record(...) -> Record | None:
    ...

async def create_record(...) -> Record:
    ...

async def delete_record(...) -> bool:
    ...

# WRONG — implicit return type
async def get_record(...):
    ...
```

This enables type checking and forces the caller to handle all cases (None, empty list, etc.).
