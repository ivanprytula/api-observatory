"""Async database engine, session factory, and dependency injection.

Why `expire_on_commit=False` — after `await session.commit()`
SQA would expire every attribute. In an async context we cannot lazily reload them
(no sync DB round-trips allowed), so `expire_on_commit=False` keeps the values in-memory
"""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from services.ingestor.config import settings
from services.ingestor.core.tenant import role_context, tenant_context


engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,  # Permanent connections in pool
    max_overflow=settings.db_max_overflow,  # Temporary connections during spikes
    pool_timeout=settings.db_pool_timeout,  # Wait time for connection
    pool_recycle=settings.db_pool_recycle,  # Prevent stale connections
    pool_pre_ping=True,  # Verify connection before use
    echo=settings.db_echo,  # SQL logging for debugging
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,  # Manual control over flushing
    expire_on_commit=False,  # Keep data accessible after commit, avoids lazy-load error
    autocommit=False,  # Require explicit commits
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency: yields a fresh async DB session per request.

    - Each request gets its own isolated session (never shared)
    - Context manager ensures cleanup (auto-close)
    - Sessions are stateless and short-lived
    - Configuration (expire_on_commit=False) is enforced at startup/code review
    """
    async with AsyncSessionLocal() as session:
        tid = tenant_context.get()
        role = role_context.get()
        if tid is not None:
            await session.execute(
                text("SELECT set_config('app.tenant_id', :tid, true)"),
                {"tid": str(tid)},
            )
        if role is not None:
            import logging

            logging.getLogger("services.ingestor.database").info(
                f"DB session setting: app.tenant_id={tid}, app.user_role={role}"
            )
            await session.execute(
                text("SELECT set_config('app.user_role', :role, true)"),
                {"role": str(role)},
            )
        yield session
