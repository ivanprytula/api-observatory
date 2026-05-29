"""Alembic environment config.

Use a SQLAlchemy sync Engine (psycopg dialect) for online migrations.
This provides a SQLAlchemy `Connection` object (with `.dialect`) which
Alembic expects. Running migrations via the Alembic CLI is a top-level
process so creating a sync engine here is safe.

See docs/gotchas.md for Python 3.14 notes and alternatives.
"""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

import services.ingestor.models  # noqa: F401 — registers all ORM models to Base.metadata
from alembic import context
from services.ingestor.config import settings
from services.ingestor.database import Base


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


target_metadata = Base.metadata


def include_object(
    object: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    """Filter which database objects Alembic autogenerate considers.

    Rules:
    - Skip any reflected table that is NOT already declared in our metadata
      (catches PostGIS extension tables, Tiger geocoder tables, partition
      children, and any other objects installed by DB extensions).
    - Skip the observations_archive_YYYYMM monthly partition children, which
      are created by raw SQL in the partitioning migration and are not
      SQLAlchemy ORM models.
    """
    if type_ == "table" and reflected and compare_to is None:
        # Table exists in DB but has no counterpart in our metadata → skip.
        return False
    if (
        type_ == "table"
        and reflected
        and name is not None
        and (name == "observations_archive" or name.startswith("observations_archive_"))
    ):
        return False
    return True


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
    """Run migrations in 'offline' mode (emit SQL)."""
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
    """Run migrations in 'online' mode using a SQLAlchemy Engine.

    We create a sync Engine using the psycopg dialect and pass a SQLAlchemy
    Connection to Alembic. This ensures `connection.dialect` exists.
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
