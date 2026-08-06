"""Configure Alembic for the inference service's independent schema."""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

import services.inference.models  # noqa: F401 — registers ORM models to Base.metadata
from alembic import context
from services.inference.config import settings
from services.inference.database import Base


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


target_metadata = Base.metadata


def include_object(
    object: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    """Ignore reflected tables that are not part of this service's metadata.

    The service normally uses a dedicated PostgreSQL database. This defensive
    guard prevents a misconfigured connection from producing destructive
    autogenerate operations against another service's tables.
    """
    if type_ != "table" or not reflected:
        return True
    return compare_to is not None


_config_url = config.get_main_option("sqlalchemy.url")
if _config_url:
    _sync_url = _config_url
else:
    _sync_url = settings.database_url.replace(
        "postgresql+asyncpg://", "postgresql+psycopg://"
    )


# Distinct version table name, even though this service now runs on its own
# dedicated Postgres instance (inference-db, ADR 015) where the default
# "alembic_version" wouldn't collide with anything: self-documenting (a stray
# `psql \dt` immediately shows which service's migration history this is),
# and free insurance if this database is ever consolidated/copied elsewhere.
_VERSION_TABLE = "inference_alembic_version"


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        version_table=_VERSION_TABLE,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_sync_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            version_table=_VERSION_TABLE,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
