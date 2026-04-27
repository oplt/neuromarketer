from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.core.config import settings
from backend.db.models import Base

_STATEMENT_TIMEOUT_MS = getattr(settings, "database_statement_timeout_ms", 30_000)
_IDLE_IN_TX_TIMEOUT_MS = getattr(
    settings, "database_idle_in_transaction_timeout_ms", 60_000
)

_connect_args: dict = {
    "server_settings": {
        "statement_timeout": str(_STATEMENT_TIMEOUT_MS),
        "idle_in_transaction_session_timeout": str(_IDLE_IN_TX_TIMEOUT_MS),
    },
}

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_pre_ping=settings.database_pool_pre_ping,
    pool_size=getattr(settings, "database_pool_size", 20),
    max_overflow=getattr(settings, "database_max_overflow", 10),
    pool_timeout=getattr(settings, "database_pool_timeout", 30),
    pool_recycle=getattr(settings, "database_pool_recycle", 1800),
    connect_args=_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    if not settings.database_auto_create:
        return

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def database_is_ready() -> bool:
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def close_db() -> None:
    await engine.dispose()
