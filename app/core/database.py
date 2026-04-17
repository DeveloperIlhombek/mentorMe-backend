from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    echo=not settings.is_production,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Public schema DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_tenant_db(tenant_slug: str) -> AsyncGenerator[AsyncSession, None]:
    """Tenant schema DB session — sets search_path automatically."""
    async with AsyncSessionLocal() as session:
        try:
            schema = f"tenant_{tenant_slug.replace('-', '_')}"
            await session.execute(text(f'SET search_path TO "{schema}", public'))
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tenant_schema(schema_name: str, session: AsyncSession) -> None:
    """Create a new PostgreSQL schema for a tenant."""
    await session.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))
    await session.commit()


# Alias — get_db_session nomi bilan ham ishlatish mumkin (public schema uchun)
get_db_session = get_db
