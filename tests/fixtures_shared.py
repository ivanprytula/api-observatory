"""Pytest fixtures for the async stack (aiosqlite in-memory or PostgreSQL).

Database selection:
  - Default: SQLite in-memory (no external dependency)
  - If DATABASE_URL_TEST env var set: Use PostgreSQL (for concurrent tests)

PostgreSQL integration tests provision a temporary container through testcontainers when Docker is
available. Set ``DATABASE_URL_TEST`` only when intentionally targeting a dedicated local test
database; it is not read from ``.env``.

IMPORTANT TESTING NOTE (parallelism):

- The default test configuration uses an in-memory SQLite database (`sqlite+aiosqlite:///:memory:`).
    This works well for local and CI single-process runs, but it is NOT safe to run tests
    in parallel with `pytest-xdist` (`-n auto`) when using the default SQLite backend because
    the in-memory database and SQLAlchemy async internals can be tied to a single event loop.

- If you need to run tests in parallel, switch to PostgreSQL for tests by setting
    `DATABASE_URL_TEST` to a PostgreSQL instance (see steps above). PostgreSQL tests use
    `NullPool` to avoid connection-pooling across event loop boundaries and are safe for
    parallel execution.

"""

import datetime
import os
import shutil
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


# ---------------------------------------------------------------------------
# Two-layer database strategy:
#   CI    → DATABASE_URL_TEST injected as a real env var by GHA service container
#   Local → testcontainers auto-provisions pgvector/pgvector:pg17 when Docker is
#           available and DATABASE_URL_TEST is NOT already a real process env var
#           (DATABASE_URL_TEST in .env is intentionally ignored here — remove it
#           from .env; it is no longer needed with testcontainers)
#   Unit  → sqlite+aiosqlite:///:memory: fallback (no Docker or Postgres needed)
#
# IMPORTANT: this block runs BEFORE load_dotenv so that a stale
# DATABASE_URL_TEST in .env cannot suppress auto-provisioning.
# ---------------------------------------------------------------------------
# (Removed module-level testcontainers startup to allow lazy provisioning)


# Tests consume only explicit process variables. Never load the developer's
# private `.env`; local defaults below keep unit tests self-contained, while
# integration jobs inject their database and cache endpoints deliberately.

# Set testing environment BEFORE any app imports
# This ensures the app loads with testing configuration.
os.environ["ENVIRONMENT"] = "testing"
# Keep rate limiting storage in-memory for deterministic tests.
os.environ["CACHE_ENABLED"] = "false"
os.environ.setdefault("SERVICE_VERSION", "test-service")
os.environ.setdefault("CONTRACTS_VERSION", "test-contracts")
os.environ["API_V1_BEARER_TOKEN"] = ""

from services.ingestor.core.auth import verify_jwt_token  # noqa: E402
from services.ingestor.core.config import Settings  # noqa: E402
from services.ingestor.core.database import Base, get_db  # noqa: E402
from services.ingestor.core.tenant import role_context, tenant_context  # noqa: E402
from services.ingestor.main import app  # noqa: E402
from tests.shared.payloads import OBSERVATION_API  # noqa: E402


# Explicit shared fixture export surface for tree-level conftest re-exports.
__all__ = [
    "observation_timestamp",
    "fake_cache",
    "cache_container",
    "real_cache",
    "client_with_cache",
    "_auto_provision_postgres",
    "apply_migrations",
    "db",
    "client",
    "client_isolated",
    "test_settings",
    "settings_with_api_token",
    "created_observation",
    "created_observations",
    "sample_observations_with_tags",
    "observation_payload",
    "postgresql_async_session",
    "postgresql_async_session_isolated",
    "mock_db_failure",
    "app_with_api_token",
    "pytest_configure",
    "pytest_collection_modifyitems",
]


# For PostgreSQL, set pool size to match concurrent test load
def _get_test_db_url() -> str:
    return os.environ.get("DATABASE_URL_TEST", "sqlite+aiosqlite:///:memory:")


def _is_postgres() -> bool:
    return "postgresql" in _get_test_db_url()


def _is_sqlite() -> bool:
    return "sqlite" in _get_test_db_url()


def _get_engine_kwargs() -> dict:
    kwargs: dict = {}
    if _is_postgres():
        # Use NullPool in tests to ensure connections are not pooled across
        # event loop boundaries. Pooling can create connections attached to a
        # different asyncio event loop, causing "Future attached to a different
        # loop" RuntimeError when pytest_asyncio switches loops between tests.
        # NullPool also makes prepared-statement caching a non-issue (each
        # connection is independent), so no connect_args override is needed.
        kwargs["poolclass"] = NullPool
    return kwargs


_engine = None
_AsyncSessionLocal = None


def _ensure_sessionmaker() -> None:
    """Lazily create the async engine and sessionmaker.

    Must be called from the test event loop (i.e., inside fixtures). Creating
    the engine at import time can bind asyncpg internals to a different
    asyncio event loop which causes "Future attached to a different loop"
    errors during testing. Creating lazily inside fixtures avoids that.
    """
    global _engine, _AsyncSessionLocal
    if _AsyncSessionLocal is None:
        _engine = create_async_engine(
            _get_test_db_url(), echo=False, **_get_engine_kwargs()
        )
        _AsyncSessionLocal = async_sessionmaker(
            bind=_engine, autocommit=False, autoflush=False, expire_on_commit=False
        )


_OBSERVATION_TIMESTAMP = datetime.datetime.fromisoformat("2026-01-01T00:00:00")

# Path to alembic.ini (repo root, one level above tests/)
_ALEMBIC_INI = Path(__file__).parent.parent / "alembic.ini"


def _alembic_upgrade(sync_url: str) -> None:
    """Run Alembic migrations to head (sync, called via asyncio.to_thread)."""
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(_ALEMBIC_INI))
    # Escape bare % signs — configparser.BasicInterpolation treats them as
    # interpolation syntax, but testcontainers passwords often contain
    # URL-encoded characters like %23.
    cfg.set_main_option("sqlalchemy.url", sync_url.replace("%", "%%"))
    command.upgrade(cfg, "head")


def _alembic_downgrade(sync_url: str) -> None:
    """Downgrade all migrations to base (sync, called via asyncio.to_thread).

    Drops and recreates the public schema to guarantee a clean slate,
    even when a prior session was interrupted before teardown ran (which
    leaves orphan tables/indexes that fool Alembic's downgrade logic).

    Re-enables pgvector after the schema recreate: this test Postgres is
    shared (session-scoped) with services/inference/tests/ when both suites
    run in the same pytest invocation, and dropping "public" also drops any
    extension created in it — without this, inference's tests fail with
    'type "vector" does not exist' whenever they run after this fixture.
    """
    import sqlalchemy as sa

    engine = sa.create_engine(sync_url)
    try:
        with engine.begin() as conn:
            conn.execute(sa.text("DROP SCHEMA public CASCADE"))
            conn.execute(sa.text("CREATE SCHEMA public"))
            conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    finally:
        engine.dispose()


async def _clear_observations(session: AsyncSession) -> None:
    """Remove seeded data without changing the migrated schema.

    On PostgreSQL this performs a `TRUNCATE ... RESTART IDENTITY CASCADE`
    across all ORM tables (fast, resets sequences). For SQLite fallback to
    per-table `DELETE` statements because SQLite does not support TRUNCATE.
    """
    if _is_postgres():
        existing_tables: list[str] = []
        for table in Base.metadata.sorted_tables:
            result = await session.execute(
                text("SELECT to_regclass(:table_name)"),
                {"table_name": table.name},
            )
            if result.scalar_one_or_none() is not None:
                existing_tables.append(table.name)

        if existing_tables:
            table_names = ", ".join(existing_tables)
            await session.execute(
                text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE")
            )
    else:
        # SQLite: delete rows from each table in reverse dependency order
        for t in reversed(Base.metadata.sorted_tables):
            await session.execute(text(f"DELETE FROM {t.name}"))
    await session.commit()


def _clear_casbin() -> None:
    """Remove all Casbin policies and role assignments from the enforcer,
    then re-seed the default RBAC role hierarchy."""
    from services.ingestor.core.auth import get_casbin_enforcer

    enforcer = get_casbin_enforcer()
    enforcer.remove_filtered_policy(0, "", "", "", "")
    enforcer.remove_filtered_grouping_policy(0, "", "", "", "")
    enforcer.add_policy("user", "*", "*", "access")
    enforcer.add_policy("manager", "*", "*", "access")
    enforcer.add_policy("admin", "*", "*", "access")
    enforcer.add_grouping_policy("admin", "manager", "*")
    enforcer.add_grouping_policy("manager", "user", "*")


# ---------------------------------------------------------------------------
# Timestamp Fixture (DRY: centralized test timestamp constant)
# ---------------------------------------------------------------------------
@pytest.fixture()
def observation_timestamp() -> datetime.datetime:
    """Canonical timestamp for observations in tests.

    Centralizes the timestamp value to reduce duplication across test files.
    Tests can inject this fixture to get a consistent, documented test timestamp.
    """
    return _OBSERVATION_TIMESTAMP


# ---------------------------------------------------------------------------
# Cache fixtures (for cache testing)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture()
async def fake_cache():
    """In-memory Redis instance for testing (uses fakeredis).

    No network calls; operates as a pure Python object.
    Perfect for CI/local testing without a real Redis instance.
    """
    import fakeredis

    cache = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield cache
    await cache.flushall()  # Clean up after test
    await cache.aclose()


@pytest.fixture(scope="session")
def cache_container():
    """Session-scoped real Redis container via testcontainers.

    Starts once per test session when Docker is available.  Integration tests
    that need actual Redis pub/sub semantics (blocking reads, channels, etc.)
    should use ``real_cache`` instead of ``fake_cache``.

    Falls back to None when Docker is not present so callers can skip.
    """
    if not shutil.which("docker"):
        yield None
        return

    from testcontainers.redis import RedisContainer

    with RedisContainer() as container:
        yield container


@pytest_asyncio.fixture()
async def real_cache(cache_container):
    """Async Redis client backed by a real Redis container.

    Use for integration tests that rely on Redis pub/sub, keyspace notifications,
    or Lua scripts — semantics that fakeredis does not fully emulate.
    Skips the test automatically if Docker is unavailable.
    """
    if cache_container is None:
        pytest.skip("Docker not available — skipping real-cache integration test")

    from redis.asyncio import Redis

    host = cache_container.get_container_host_ip()
    port = int(cache_container.get_exposed_port(6379))
    client = Redis(host=host, port=port, decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()


@pytest_asyncio.fixture()
async def client_with_cache(
    db: AsyncSession, fake_cache
) -> AsyncGenerator[AsyncClient]:
    """Async HTTPX client with DB + Redis cache dependencies overridden.

    Injects fakeredis into app cache module so cache operations work in tests.
    """
    from services.ingestor import cache
    from services.ingestor.main import app  # Import here to avoid circular imports

    _ensure_sessionmaker()

    async def _override_db() -> AsyncGenerator[AsyncSession]:
        _ensure_sessionmaker()
        assert _AsyncSessionLocal is not None, "_AsyncSessionLocal not initialized"
        SessionLocal = _AsyncSessionLocal  # type: ignore[assignment]
        async with SessionLocal() as session:  # type: ignore[call-arg]
            yield session

    # Override both DB and cache
    app.dependency_overrides[get_db] = _override_db

    async def _mock_jwt() -> dict:
        return {"sub": "testuser"}

    app.dependency_overrides[verify_jwt_token] = _mock_jwt

    # Seed Casbin so casbin_guard allows the default test user.
    from services.ingestor.core.auth import get_casbin_enforcer

    enforcer = get_casbin_enforcer()
    enforcer.add_role_for_user_in_domain("testuser", "admin", "*")

    # Inject fake cache into cache module and auth module
    cache._client = fake_cache
    from services.ingestor.core import auth

    auth._session_client = fake_cache

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    # Cleanup
    app.dependency_overrides.clear()
    cache._client = None


# ---------------------------------------------------------------------------
# Database Auto-provisioning & Schema Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def _auto_provision_postgres() -> Generator[None]:
    """Auto-provision a Postgres container if DATABASE_URL_TEST is missing.

    Only starts if a database-dependent fixture is requested.
    """
    if "DATABASE_URL_TEST" not in os.environ and shutil.which("docker"):
        from testcontainers.community.postgres import PostgresContainer  # noqa: PLC0415

        tc = PostgresContainer("pgvector/pgvector:pg17")
        tc.start()
        os.environ["DATABASE_URL_TEST"] = tc.get_connection_url().replace(
            "postgresql+psycopg2://", "postgresql+asyncpg://"
        )
        try:
            yield
        finally:
            tc.stop()
    else:
        yield


@pytest.fixture(scope="session")
def apply_migrations(_auto_provision_postgres: None) -> Generator[None]:
    """Apply Alembic migrations once per test session (PostgreSQL only).

    Ensures the test DB has the exact same schema as production.
    No longer 'autouse=True' to avoid side-effects for unit tests.
    """
    if not _is_postgres():
        yield
        return

    _ensure_sessionmaker()
    sync_url = _get_test_db_url().replace(
        "postgresql+asyncpg://", "postgresql+psycopg://"
    )
    _alembic_downgrade(sync_url)
    _alembic_upgrade(sync_url)

    # Create the non-superuser role for RLS testing
    # This role is used by the client fixture to ensure RLS is enforced
    import sqlalchemy as sa

    engine = sa.create_engine(sync_url)
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles "
                "WHERE rolname = 'test_app_api_user') "
                "THEN CREATE ROLE test_app_api_user; "
                "END IF; END $$;"
            )
        )
        conn.execute(
            sa.text(
                "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO test_app_api_user;"
            )
        )
        conn.execute(
            sa.text(
                "GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO test_app_api_user;"
            )
        )
        conn.execute(sa.text("GRANT USAGE ON SCHEMA public TO test_app_api_user;"))
        conn.execute(
            sa.text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                "GRANT ALL ON TABLES TO test_app_api_user;"
            )
        )
        conn.execute(
            sa.text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                "GRANT ALL ON SEQUENCES TO test_app_api_user;"
            )
        )
        conn.execute(
            sa.text(
                "GRANT INSERT, SELECT, UPDATE, DELETE ON tenants TO test_app_api_user"
            )
        )

    yield
    _alembic_downgrade(sync_url)


@pytest_asyncio.fixture()
async def db(apply_migrations: None) -> AsyncGenerator[AsyncSession]:
    """Yield an async session with a clean-data slate."""
    _ensure_sessionmaker()
    assert _engine is not None, "_engine not initialized"
    assert _AsyncSessionLocal is not None, "_AsyncSessionLocal not initialized"

    _clear_casbin()

    if not _is_postgres():
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with _AsyncSessionLocal() as session:
        yield session

    if _is_postgres():
        async with _AsyncSessionLocal() as cleanup:
            await _clear_observations(cleanup)
    else:
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def client(db: AsyncSession, fake_cache) -> AsyncGenerator[AsyncClient]:
    """Async HTTPX client with DB dependency overridden.

    For PostgreSQL (and general robustness), provide a fresh `AsyncSession`
    for each HTTP request by using the module-level `_AsyncSessionLocal`.
    The `db` fixture is still depended-on to ensure schema creation.
    """

    # Ensure the module-level sessionmaker is created on the active test event loop
    _ensure_sessionmaker()

    async def _override() -> AsyncGenerator[AsyncSession]:
        # Defensive: ensure sessionmaker initialized (may be None if not created)
        _ensure_sessionmaker()
        assert _AsyncSessionLocal is not None, "_AsyncSessionLocal not initialized"
        SessionLocal = _AsyncSessionLocal  # type: ignore[assignment]

        # Provide a fresh session for each request to avoid sharing a single
        # session across concurrent requests (which causes asyncpg errors).
        async with SessionLocal() as session:  # type: ignore[call-arg]
            tid = tenant_context.get()
            role = role_context.get()
            if tid is not None:
                await session.execute(
                    text("SELECT set_config('app.tenant_id', :tid, true)"),
                    {"tid": str(tid)},
                )
            if role is not None:
                await session.execute(
                    text("SELECT set_config('app.user_role', :role, true)"),
                    {"role": str(role)},
                )
            if _is_postgres():
                # Force non-superuser role to ensure RLS is enforced.
                # Superusers (like 'postgres') bypass RLS.
                await session.execute(text("SET ROLE test_app_api_user"))
            yield session

    app.dependency_overrides[get_db] = _override

    async def _mock_jwt() -> dict:
        return {"sub": "testuser"}

    app.dependency_overrides[verify_jwt_token] = _mock_jwt

    from services.ingestor.core.auth import get_casbin_enforcer

    enforcer = get_casbin_enforcer()
    enforcer.add_role_for_user_in_domain("testuser", "admin", "*")

    from services.ingestor.core import auth

    auth._session_client = fake_cache

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()
    auth._session_client = None


@pytest_asyncio.fixture()
async def client_isolated(
    postgresql_async_session_isolated: AsyncSession,
) -> AsyncGenerator[AsyncClient]:
    """Async HTTPX client with isolated PostgreSQL session (no connection pooling).

    Use for concurrent tests to avoid asyncpg "another operation in progress" errors.
    Each HTTP request gets independent DB connection. Skips if PostgreSQL unavailable.
    """
    # Store the sessionmaker from the isolated session so we can create fresh sessions
    SessionLocal = postgresql_async_session_isolated._sessionmaker

    async def _override() -> AsyncGenerator[AsyncSession]:
        # Create a FRESH session for each HTTP request (critical for concurrent tests!)
        async with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Settings Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def test_settings() -> Settings:
    """Override app settings for testing.

    Useful for tests that need to verify different configurations.
    """
    return Settings(
        environment="testing",
        app_version="1.0.0-test",
        api_v1_bearer_token=None,
        jwt_secret="test-secret-key-32-chars-minimum!!",
        db_echo=False,
    )


@pytest.fixture()
def settings_with_api_token() -> Settings:
    """Settings with API v1 bearer token enabled."""
    return Settings(
        environment="testing",
        api_v1_bearer_token="test-bearer-token-123",
        db_echo=False,
    )


# ---------------------------------------------------------------------------
# Observation Fixtures (pre-populated observations for testing)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture()
async def created_observation(client: AsyncClient) -> dict:
    """Create and return a single valid observation."""
    response = await client.post("/api/v1/observations", json=OBSERVATION_API)
    return response.json()


@pytest_asyncio.fixture()
async def created_observations(client: AsyncClient) -> list[dict]:
    """Create and return multiple observations."""
    observations = []
    for i in range(3):
        payload = {
            **OBSERVATION_API,
            "source": f"source-{i}",
            "tags": ["test", f"observation-{i}"],
        }
        response = await client.post("/api/v1/observations", json=payload)
        observations.append(response.json())
    return observations


@pytest_asyncio.fixture()
async def sample_observations_with_tags(db: AsyncSession) -> list:
    """Create sample observations with varying tag counts for testing queries.

    Useful for N+1 demo and other query optimization tests.
    Creates observations with 0, 2, 4, 6, 8 tags respectively.
    """
    from services.ingestor.api_schemas.observations import ObservationRequest
    from services.ingestor.repositories.observations import create_observation

    observations = []
    for i in range(5):
        request = ObservationRequest(
            source=f"sample-{i}",
            timestamp=_OBSERVATION_TIMESTAMP,
            data={"index": i},
            tags=[f"tag-{j}" for j in range(i * 2)],  # 0, 2, 4, 6, 8 tags
        )
        observation = await create_observation(db, request)
        observations.append(observation)
    return observations


@pytest_asyncio.fixture()
async def observation_payload() -> dict:
    """Valid observation payload for testing."""
    return OBSERVATION_API.copy()


# ---------------------------------------------------------------------------
# PostgreSQL Fixture (for EXPLAIN ANALYZE tests)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture()
async def postgresql_async_session(
    apply_migrations: None,
) -> AsyncGenerator[AsyncSession]:
    """Yield PostgreSQL session for query-plan integration tests.

    Uses the shared test URL selection strategy:
    - Local: testcontainers sets DATABASE_URL_TEST when Docker is available.
    - CI: GitHub Actions service container sets DATABASE_URL_TEST explicitly.
    - SQLite fallback: fixture skips gracefully.

    The migrated schema is managed by the session-scoped apply_migrations
    fixture, so this fixture only clears test data before/after each test.
    """
    if os.environ.get("ALLOW_EXPLAIN_ANALYZE", "").lower() != "true":
        pytest.skip(
            "EXPLAIN ANALYZE tests are opt-in only. "
            "Set ALLOW_EXPLAIN_ANALYZE=true to run against a local PostgreSQL instance. "
            "Never run against a remote, staging, or production database."
        )
    if not _is_postgres():
        pytest.skip(
            "PostgreSQL not available for EXPLAIN ANALYZE tests. "
            "Set DATABASE_URL_TEST or run with Docker enabled for testcontainers."
        )

    test_engine = create_async_engine(_get_test_db_url(), echo=False)
    try:
        async with test_engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip(
            "PostgreSQL URL is configured but not reachable. "
            "Ensure the test DB is up and healthy before running this test file."
        )
    finally:
        await test_engine.dispose()

    _ensure_sessionmaker()
    assert _AsyncSessionLocal is not None, "_AsyncSessionLocal not initialized"

    async with _AsyncSessionLocal() as cleanup_session:
        await _clear_observations(cleanup_session)

    async with _AsyncSessionLocal() as session:
        yield session

    async with _AsyncSessionLocal() as cleanup_session:
        await _clear_observations(cleanup_session)


@pytest_asyncio.fixture()
async def postgresql_async_session_isolated(
    apply_migrations: None,
) -> AsyncGenerator[AsyncSession]:
    """PostgreSQL-only fixture: Fresh engine + session per test (no connection pooling).

    Use for concurrent tests to avoid asyncpg "another operation in progress" errors.
    Skips if DATABASE_URL_TEST not set or points to SQLite.

    Each test gets isolated connection — no connection pooling/reuse within test.
    Solves: asyncpg cannot handle concurrent operations on same connection.
    """
    db_url = os.environ.get("DATABASE_URL_TEST")
    if not db_url or "sqlite" in db_url:
        pytest.skip(
            "DATABASE_URL_TEST not set or SQLite in use. "
            "Concurrent tests require PostgreSQL. "
            "Enable Docker/testcontainers or set DATABASE_URL_TEST explicitly."
        )

    # Create isolated engine — NO connection pooling (pool_size=1, max_overflow=0)
    # This ensures each test gets a fresh connection without reuse conflicts
    isolated_engine = create_async_engine(
        db_url,
        echo=False,
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,  # Validate connections before use
    )

    # Create session (expires_on_commit=False required for async)
    # Define before try block to avoid "unbound variable" in finally
    SessionLocal = async_sessionmaker(
        isolated_engine,
        expire_on_commit=False,
        autoflush=False,
    )

    # Create session against the already-migrated test database schema.
    try:
        async with isolated_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with SessionLocal() as cleanup_session:
            await _clear_observations(cleanup_session)

        async with SessionLocal() as session:
            # Store sessionmaker on the session for use by client_isolated
            session._sessionmaker = SessionLocal  # type: ignore[attr-defined]
            yield session
    finally:
        # Cleanup data only. The migrated schema is shared across tests and
        # owned by Alembic, so dropping tables here would break materialized
        # views and other dependent objects.
        async with SessionLocal() as cleanup_session:
            await _clear_observations(cleanup_session)
        await isolated_engine.dispose()


# ---------------------------------------------------------------------------
# Mock/Override Fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture()
async def mock_db_failure() -> AsyncGenerator[AsyncMock]:
    """Mock database that raises RuntimeError on execute().

    Use with app.dependency_overrides[get_db] to simulate DB failure.
    """
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute.side_effect = RuntimeError("Database connection lost")
    yield mock_session


@pytest.fixture()
def app_with_api_token(settings_with_api_token: Settings):
    """FastAPI app with API token authentication enabled."""
    with patch("app.main.settings", settings_with_api_token):
        yield app


# ---------------------------------------------------------------------------
# Pytest Hooks & Configuration
# ---------------------------------------------------------------------------
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "postgresonly: mark test to run only when PostgreSQL is available "
        "(skip on SQLite in-memory)",
    )


def pytest_collection_modifyitems(config, items):
    """Auto-skip PostgreSQL-only tests when using SQLite.

    Tests marked with @pytest.mark.postgresonly will skip if PostgreSQL
    is not available (no DATABASE_URL_TEST and no Docker for testcontainers).
    """
    # If we have a URL already OR we can auto-provision via Docker, we have Postgres.
    has_postgres = "postgresql" in os.environ.get("DATABASE_URL_TEST", "") or bool(
        shutil.which("docker")
    )

    if not has_postgres:
        skip_marker = pytest.mark.skip(
            reason="PostgreSQL not available (no DATABASE_URL_TEST and no Docker). "
            "Run with Docker enabled or set DATABASE_URL_TEST to enable these tests."
        )
        for item in items:
            if "postgresonly" in item.keywords:
                item.add_marker(skip_marker)
