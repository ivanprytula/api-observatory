"""Configure Alembic for the ingestor schema.

Alembic invokes this module as a top-level process. Migrations therefore use
SQLAlchemy's synchronous PostgreSQL driver, while the application can keep its
async driver for request handling. The metadata import registers every ORM
model before autogenerate or migration execution begins.
"""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

import services.ingestor.models  # noqa: F401 — registers all ORM models to Base.metadata
from alembic import context
from services.ingestor.core.config import settings
from services.ingestor.core.database import Base


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


target_metadata = Base.metadata


def include_object(
    object: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    """Keep autogenerate focused on tables owned by this schema.

    Reflected tables without ORM counterparts are ignored so extension-owned
    tables and the monthly archive partitions created by SQL migrations are
    not treated as application-owned tables.
    """
    # Only filter tables; non-table objects are included.
    if type_ != "table" or not reflected:
        return True

    # Table exists in DB but has no counterpart in our metadata → skip.
    if compare_to is None:
        return False

    # Skip the observations archive partitions created outside ORM migrations.
    return not (
        name is not None
        and (name == "observations_archive" or name.startswith("observations_archive_"))
    )


# URL priority: programmatic override (testing) > app settings (production).
# Programmatic callers set sqlalchemy.url via config.set_main_option() before
# invoking alembic.command.upgrade/downgrade so they can target a different DB
# (e.g. test_database) without touching application environment variables.
_config_url = config.get_main_option("sqlalchemy.url")
if _config_url:
    _sync_url = _config_url
else:
    # Convert app async URL into a SQLAlchemy sync psycopg URL.
    # Example: postgresql+asyncpg://... -> postgresql+psycopg://...
    _sync_url = settings.database_url.replace(
        "postgresql+asyncpg://", "postgresql+psycopg://"
    )


def run_migrations_offline() -> None:
    """Render migration SQL without opening a database connection."""
    context.configure(
        url=_sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations using a short-lived synchronous SQLAlchemy engine.

    Alembic receives a real connection so dialect-specific operations and
    transactional migration steps work as expected.
    """
    connectable = create_engine(_sync_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
