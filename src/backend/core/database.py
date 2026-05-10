# src/backend/core/database.py
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from src.backend.config import settings


# base class for all models
class Base(DeclarativeBase):
    pass


# ceate async engine
if settings.DATABASE_URL.startswith("sqlite"):
    # convert sqlite:/// to sqlite+aiosqlite:///
    db_url = settings.DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///")
else:
    db_url = settings.DATABASE_URL

engine = create_async_engine(db_url, echo=settings.DB_ECHO, future=True)

# session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # prevent expired obj errors
    autocommit=False,
    autoflush=False,
)


async def init_db() -> None:
    """create all tables on startup"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """clean up engine on shut down"""
    await engine.dispose()


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get database session for dependency injection

    Usage:
        async with get_session() as session:
            session.add(obj)
            await session.commit()
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# for fastapi depends
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """fastapi dependency for db sessions"""
    async with get_session() as session:
        yield session
