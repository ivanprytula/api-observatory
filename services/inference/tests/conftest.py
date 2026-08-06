"""Pytest fixtures for the inference service's test suite.

pgvector requires real Postgres (no SQLite fallback like the ingestor's
tests have) — reuses the shared `_auto_provision_postgres` testcontainers
fixture (pgvector/pgvector:pg17) from the app repo's fixtures_shared.py, then
applies this service's own Alembic migrations and builds an isolated
engine/sessionmaker, mirroring the ingestor test suite's pattern of
overriding `get_db` rather than touching the app's module-level engine.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


pytest_plugins = ["tests.fixtures_shared"]

_ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"


def _get_test_db_url() -> str:
    return os.environ.get("DATABASE_URL_TEST", "")


def _alembic_upgrade(sync_url: str) -> None:
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(_ALEMBIC_INI))
    # Escape bare % signs — configparser.BasicInterpolation treats them as
    # interpolation syntax, but testcontainers passwords often contain
    # URL-encoded characters like %23.
    cfg.set_main_option("sqlalchemy.url", sync_url.replace("%", "%%"))
    command.upgrade(cfg, "head")


def _alembic_downgrade(sync_url: str) -> None:
    """Downgrade *only this service's own tables* to a clean slate.

    Deliberately not `DROP SCHEMA public CASCADE` (unlike the ingestor's
    equivalent in tests/fixtures_shared.py): this service's tests share the
    session-scoped test Postgres with the ingestor's own test suite when
    both run in the same pytest invocation. Nuking the whole schema here
    would silently wipe the ingestor's tables mid-session — exactly the
    kind of cross-service blast radius the migration environment guards
    against during autogenerate; this is the same guard for
    the test teardown path.
    """
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", sync_url.replace("%", "%%"))
    command.downgrade(cfg, "base")


def _ensure_vector_extension(sync_url: str) -> None:
    """Enable pgvector before applying migrations that declare Vector columns."""
    import sqlalchemy as sa

    engine = sa.create_engine(sync_url)
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def apply_inference_migrations(_auto_provision_postgres: None) -> Generator[None]:
    """Apply this service's own Alembic migrations once per test session."""
    sync_url = _get_test_db_url().replace(
        "postgresql+asyncpg://", "postgresql+psycopg://"
    )
    _alembic_downgrade(sync_url)
    _ensure_vector_extension(sync_url)
    _alembic_upgrade(sync_url)
    yield


@pytest_asyncio.fixture()
async def db(apply_inference_migrations: None) -> AsyncGenerator[AsyncSession]:
    """Isolated async session against the test Postgres, using NullPool to
    avoid cross-event-loop connection reuse between tests."""
    engine = create_async_engine(_get_test_db_url(), poolclass=NullPool)
    session_local = async_sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    async with session_local() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture()
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient]:
    """Async HTTPX client for the inference FastAPI app, DB dependency
    overridden to the test session (mirrors the ingestor test client)."""
    from services.inference.database import get_db
    from services.inference.main import app

    async def _override() -> AsyncGenerator[AsyncSession]:
        yield db

    app.dependency_overrides[get_db] = _override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture()
def mock_embeddings():
    """Deterministic fake embedder — no network/model download in tests.

    Produces vectors whose cosine similarity reflects simple lexical overlap
    of the input words, so ranking assertions are meaningful without a real
    model: each unique word maps to a fixed pseudo-random direction, and a
    text's vector is the (normalized) sum of its words' directions.
    """
    import hashlib
    import math

    from services.inference.config import settings

    dim = settings.embedding_dim

    def _word_vector(word: str) -> list[float]:
        seed = int(hashlib.sha256(word.lower().encode()).hexdigest(), 16)
        vec = []
        for _i in range(dim):
            seed, val = divmod(seed * 1103515245 + 12345, 2**31)
            vec.append((val / 2**31) * 2 - 1)
        return vec

    def _embed(text: str) -> list[float]:
        words = text.lower().split()
        summed = [0.0] * dim
        for word in words:
            for i, v in enumerate(_word_vector(word)):
                summed[i] += v
        norm = math.sqrt(sum(v * v for v in summed)) or 1.0
        return [v / norm for v in summed]

    def _embed_texts(texts: list[str]) -> list[list[float]]:
        return [_embed(t) for t in texts]

    def _embed_query(text: str) -> list[float]:
        return _embed(text)

    with (
        patch("services.inference.search.embed_texts", side_effect=_embed_texts),
        patch("services.inference.search.embed_query", side_effect=_embed_query),
    ):
        yield
