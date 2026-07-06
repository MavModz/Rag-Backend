"""Alembic environment.

Resolves the database URL from app settings (or ``-x db_url=...``), targets the
full platform metadata (``app.platform.db.all_models``), and supports both async
drivers (asyncpg — production/runtime) and sync drivers (sqlite/psycopg — used to
autogenerate migrations without a live Postgres).
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import settings
from app.platform.db.all_models import metadata as target_metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _resolve_url() -> str:
    x_args = context.get_x_argument(as_dictionary=True)
    return x_args.get("db_url") or settings.postgres_url


def _is_async(url: str) -> bool:
    return "+asyncpg" in url or "+aiosqlite" in url


def run_migrations_offline() -> None:
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations(url: str) -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = url
    engine = async_engine_from_config(
        section, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    url = _resolve_url()
    if _is_async(url):
        asyncio.run(_run_async_migrations(url))
        return
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = url
    engine = engine_from_config(
        section, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with engine.connect() as connection:
        _do_run_migrations(connection)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
