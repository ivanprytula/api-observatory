"""Async database engine, session factory, and dependency injection.

Mirrors `services.ingestor.database`'s pattern (own Base, own engine) —
deliberately not shared: `inference` runs on its own dedicated Postgres
instance (`inference-db`, see ADR 015), not the ingestor's `ingestor-db`.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from services.inference.config import settings


engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
    pool_pre_ping=True,
    echo=settings.db_echo,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency: yields a fresh async DB session per request."""
    async with AsyncSessionLocal() as session:
        yield session
