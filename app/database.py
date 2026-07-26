"""
app/database.py
─────────────────────────────────────────────────────────
Async SQLAlchemy engine + session factory.
Switches between local SQLite and PostgreSQL (Supabase)
based on the USE_LOCAL_DB environment flag.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings


def _build_engine():
    settings = get_settings()
    url = settings.effective_database_url

    # PostgreSQL / Supabase connection pooler mode (Port 6543)
    return create_async_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=0,
        pool_recycle=300,
        pool_timeout=10,
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        },
        echo=False,
    )


engine = _build_engine()

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    """FastAPI dependency — yields an async DB session, always closed after request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """
    Create all tables and pgvector extension for PostgreSQL.
    """
    async with engine.begin() as conn:
        await conn.execute(__import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    
    # Run inline seed check if CropCanon is empty (non-recursive)
    async with AsyncSessionLocal() as session:
        try:
            from sqlalchemy import select
            from app.models import CropCanon
            res = await session.execute(select(CropCanon).limit(1))
            if not res.scalar_one_or_none():
                from scripts.seed_db import seed_data
                await seed_data(session)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Auto-seed check failed: {e}")


