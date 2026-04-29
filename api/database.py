"""Async SQLAlchemy engine + session factory.

DATABASE_URL .env orqali boshqariladi. Quyidagi sxemalarni qo'llab-quvvatlaydi:

- `sqlite+aiosqlite:///./muhsina_test.db` — lokal develop / unit-test
- `postgresql+asyncpg://user:pass@host:5432/dbname` — production

`postgresql://` yoki `sqlite:///` ko'rinishidagi sync URL'lar avtomatik async
drayverga aylantiriladi (developer .env'da unutib qoldirgan bo'lsa).

Pool sozlamalari ham drayverga moslab tanlanadi: SQLite uchun NullPool, Postgres
uchun esa AsyncAdaptedQueuePool (default).
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.pool import NullPool

from api.config import settings


# ── URL normalize ─────────────────────────────────────────

def _normalize_async_url(url: str) -> str:
    """Sync drayver URL'larni async ga aylantirish."""
    if not url:
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return url


DATABASE_URL = _normalize_async_url(settings.DATABASE_URL)
IS_SQLITE = "sqlite" in DATABASE_URL
IS_POSTGRES = "postgres" in DATABASE_URL


# ── Engine ────────────────────────────────────────────────

_engine_kwargs: dict = {"echo": settings.DEBUG}

if IS_SQLITE:
    # SQLite same-thread cheklovini async uchun olib tashlaymiz
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
    _engine_kwargs["poolclass"] = NullPool
elif IS_POSTGRES:
    # Production uchun aql-idrok bilan tanlangan pool
    _engine_kwargs["pool_size"] = 10
    _engine_kwargs["max_overflow"] = 20
    _engine_kwargs["pool_pre_ping"] = True       # eski connection'larni avtomatik tekshirish
    _engine_kwargs["pool_recycle"] = 1800        # 30 daq'dan keyin connection yangilanadi

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


# ── DI ────────────────────────────────────────────────────

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# ── Optional schema bootstrap ────────────────────────────

async def create_tables() -> None:
    """Lokal SQLite uchun jadvallarni yaratish (developer ergonomikasi).

    PRODUCTION (Postgres) muhitida Alembic orqali migration yuritiladi:
        alembic upgrade head

    Bu funksiya faqat SQLite muhitida ishlaganda jadvallarni yaratadi
    (alembic ishlatishni unutgan develop sessiyalarini buzmaslik uchun).
    """
    if not IS_SQLITE:
        return

    from sqlalchemy import text
    from database.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # SQLite ni eski develop muhitlari uchun idempotent fallback
        for stmt in (
            "ALTER TABLE users ADD COLUMN selected_branch_id INTEGER REFERENCES branches(id)",
        ):
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass  # column allaqachon mavjud


async def ping() -> bool:
    """Health check — DB ga bog'lana olishni tekshiradi."""
    from sqlalchemy import text
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return True
