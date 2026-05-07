"""DB sxemasini model bilan sinxronlash (idempotent).

Mavjud DB'da bo'lmagan ustunlarni `ALTER TABLE ADD COLUMN` orqali qo'shadi.
Yangi jadvallarni `Base.metadata.create_all` orqali yaratadi.
Oxirida `alembic stamp head` chaqiradi — kelajak deploy'lar to'g'ri ishlashi uchun.

Foydalanish:
    python scripts/sync_schema.py
"""
from __future__ import annotations

import asyncio
import sys
import subprocess

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Loyiha ildiziga path
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.config import settings
from api.database import _normalize_async_url
from database.models import Base


async def main() -> None:
    url = _normalize_async_url(settings.DATABASE_URL)
    is_sqlite = "sqlite" in url
    print(f"[sync_schema] DATABASE: {url}")
    print(f"[sync_schema] dialect: {'sqlite' if is_sqlite else 'postgres'}")

    engine = create_async_engine(url, echo=False)

    # 1. create_all — yangi jadvallarni yaratadi (mavjud bo'lganlarni o'tkazib yuboradi)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[sync_schema] ✓ create_all bajarildi (yangi jadvallar yaratildi)")

    # 2. Mavjud jadvallar uchun missing ustunlarni topib qo'shamiz
    async with engine.connect() as conn:
        def get_existing_columns(sync_conn) -> dict[str, set[str]]:
            insp = inspect(sync_conn)
            return {t: {c["name"] for c in insp.get_columns(t)} for t in insp.get_table_names()}
        existing = await conn.run_sync(get_existing_columns)

    print(f"[sync_schema] mavjud jadvallar: {len(existing)}")

    # Modeldagi har jadval bo'yicha ustunlarni solishtiramiz
    added = 0
    async with engine.begin() as conn:
        for table_name, table in Base.metadata.tables.items():
            if table_name not in existing:
                continue   # create_all yaratgan bo'lishi kerak
            current_cols = existing[table_name]
            for col in table.columns:
                if col.name in current_cols:
                    continue
                # Type'ni dialektga moslab compile qilamiz
                col_type = col.type.compile(dialect=engine.dialect)
                nullable = "" if col.nullable else " NOT NULL"
                default = ""
                if col.server_default is not None:
                    default = f" DEFAULT {col.server_default.arg}"
                elif col.default is not None and col.default.is_scalar:
                    val = col.default.arg
                    if isinstance(val, bool):
                        default = f" DEFAULT {'1' if val else '0'}"
                    elif isinstance(val, (int, float)):
                        default = f" DEFAULT {val}"
                    elif isinstance(val, str):
                        default = f" DEFAULT '{val}'"
                stmt = f'ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type}{nullable}{default}'
                try:
                    await conn.execute(text(stmt))
                    print(f"[sync_schema]   + {table_name}.{col.name} ({col_type})")
                    added += 1
                except Exception as e:
                    print(f"[sync_schema]   ! {table_name}.{col.name} — xato: {e}")

    print(f"[sync_schema] {added} ta yangi ustun qo'shildi")

    await engine.dispose()

    # 3. Alembic stamp head — kelajak migration'lar uchun to'g'ri start
    print("[sync_schema] alembic stamp head...")
    res = subprocess.run(["alembic", "stamp", "head"], capture_output=True, text=True)
    print(res.stdout)
    if res.returncode != 0:
        print(f"[sync_schema] ! alembic stamp xato: {res.stderr}")
    else:
        print("[sync_schema] ✓ alembic stamp head bajarildi")


if __name__ == "__main__":
    asyncio.run(main())
