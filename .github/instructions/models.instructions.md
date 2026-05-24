---
description: "Use when adding, modifying, or reviewing SQLAlchemy ORM models. Covers SQLAlchemy 2.0 mapped_column style, column conventions, index patterns, and the required Alembic migration step."
applyTo: "app/models.py"
---

# ORM Model Conventions

## Column Style — SQLAlchemy 2.0 Only

Always use `Mapped[T]` + `mapped_column()`. Never use legacy `Column()`:

```python
# CORRECT
id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
source: Mapped[str] = mapped_column(String(255), nullable=False)
processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

# WRONG — legacy style, do not use
id = Column(Integer, primary_key=True)
```

## Nullable Convention

- `nullable=False` on all required columns — be explicit, don't rely on ORM defaults
- `nullable=True` only on genuinely optional columns (e.g. `updated_at` before first update)

## Timestamps

Use timezone-aware UTC internally, strip `tzinfo` before storing (SQLite/asyncpg compatibility):

```python
from datetime import UTC, datetime

created_at: Mapped[datetime] = mapped_column(
    DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None), nullable=False
)
```

## Composite Indexes

Define multi-column indexes in `__table_args__`, not via `index=True` on individual columns:

```python
__table_args__ = (Index("idx_records_source_timestamp", "source", "timestamp"),)
```

Use `index=True` on single-column indexes only (e.g. `primary_key=True, index=True`).

## After Any Model Change

**Always create an Alembic migration.** Run:

```bash
uv run alembic revision --autogenerate -m "<describe_change>"
uv run alembic upgrade head
```

If Alembic is not yet set up, use `/alembic-migration` to scaffold the full async setup first.

> Do NOT rely on `Base.metadata.create_all` for schema changes — it won't alter existing tables.
