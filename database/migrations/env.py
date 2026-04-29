"""Alembic environment — async-friendly va DATABASE_URL ga moslab.

DATABASE_URL .env'dan o'qiladi va asyncpg/psycopg2 yoki aiosqlite/sqlite
drayverlari avtomatik aniqlanadi. SQLite bo'lsa render_as_batch=True yoqiladi
(SQLite ALTER TABLE cheklovlarini hal qilish uchun).
"""
from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Loyihaning ildiziga sys.path qo'shamiz — `database` va `api` import uchun
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Modellarni import qilish — autogenerate metadata'ni shu yerdan oladi
from database.models import Base  # noqa: E402
from api.config import settings  # noqa: E402

config = context.config


def _to_async_url(url: str) -> str:
    """Sync drivers'ni async ga aylantirish (asyncpg/aiosqlite)."""
    if not url:
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return url


# Async URL'ni alembic config'ga yozamiz (alembic.ini default'ini bosib o'tkazamiz)
config.set_main_option("sqlalchemy.url", _to_async_url(settings.DATABASE_URL))

if config.config_file_name is not None:
    try:
        fileConfig(config.config_file_name)
    except Exception:
        # Agar logging config konfliktda bo'lsa — sokin o'tkazib yuboramiz
        pass

target_metadata = Base.metadata


def _is_sqlite() -> bool:
    return "sqlite" in (config.get_main_option("sqlalchemy.url") or "")


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql` rejimi — DB bog'lanmaysiz, faqat SQL chiqaradi."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_is_sqlite(),
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=_is_sqlite(),
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
