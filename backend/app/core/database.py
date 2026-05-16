from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import settings

logger = structlog.get_logger(__name__)

# Use server_settings to set search_path at the protocol level.
# The event-listener approach (SET search_path via cursor.execute) is unreliable
# with asyncpg because asyncpg uses binary protocol and prepared statement caching.
# server_settings is applied before any query and persists for the connection lifetime.
_CONNECT_ARGS = {
    "server_settings": {
        "search_path": f"public,{settings.database_schema}",
    }
}

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    connect_args=_CONNECT_ARGS,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def celery_db():
    """Fresh DB session for Celery tasks — NullPool avoids event-loop reuse issues.

    Each asyncio.run() in a Celery task creates a new event loop. Using the
    global pooled engine causes 'Future attached to a different loop' errors
    because asyncpg connections are bound to the loop that created them.
    NullPool creates/destroys connections per-request, safe across loop boundaries.
    """
    task_engine = create_async_engine(
        settings.database_url, poolclass=NullPool, connect_args=_CONNECT_ARGS
    )
    session_factory = async_sessionmaker(
        bind=task_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    await task_engine.dispose()


async def create_schema() -> None:
    """Create the exam_svc schema if it does not exist (run at startup)."""
    async with engine.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {settings.database_schema}"))
        await conn.execute(text(f"SET search_path TO public, {settings.database_schema}"))
