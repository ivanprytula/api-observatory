"""Ingestor service — write-side CQRS, record ingestion and Postgres owner.

Entry point: ``uvicorn ingestor.main:app``

Key submodules:
- main: FastAPI app, lifespan hook
- crud: async CRUD functions (AsyncSession as first arg)
- models: SQLAlchemy 2.0 ORM (Mapped[T] style)
- schemas: Pydantic v2 request/response schemas
- database: engine, sessionmaker, get_db dependency
- cache: Redis single-record and list cache, distributed lock
- jobs: APScheduler background jobs
"""
