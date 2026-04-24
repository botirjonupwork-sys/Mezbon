from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from api.config import settings

connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args=connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def create_tables():
    from database.models import Base
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Idempotent migrations for new columns on existing tables
        for stmt in (
            "ALTER TABLE users ADD COLUMN selected_branch_id INTEGER REFERENCES branches(id)",
        ):
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass  # column already exists
