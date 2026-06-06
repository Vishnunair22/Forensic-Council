"""
Alembic Environment — Forensic Council
========================================

Versioned database migrations. The schema is hand-written DDL (raw asyncpg,
no SQLAlchemy ORM), so `target_metadata=None` is intentional and correct.

Usage:
    alembic upgrade head          # Apply all pending migrations
    alembic downgrade -1          # Roll back one migration
    alembic revision -m "description"  # New manual migration (NOT --autogenerate)
    alembic history               # Show migration history

NOTE: `--autogenerate` is NOT supported. target_metadata=None means alembic
has no ORM model to diff against and will always produce an empty migration.
Write DDL manually in every new migration file.
"""

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Alembic config object
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Database URL — same logic as core/config.py
# ---------------------------------------------------------------------------

def _get_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if url:
        # Convert postgres:// to postgresql+asyncpg://
        url = url.replace("postgres://", "postgresql+asyncpg://")
        url = url.replace("postgresql://", "postgresql+asyncpg://")
        return url

    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "forensic_council")
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "postgres")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generate SQL without DB connection)."""
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=None,  # intentional: raw asyncpg, no ORM models
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = create_async_engine(
        _get_database_url(),
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=None)  # intentional: no ORM
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
