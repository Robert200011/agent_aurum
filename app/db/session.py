"""Async SQLAlchemy engine and request-scoped session utilities."""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


def reset_database_runtime() -> None:
    """Drop process-local database factories without touching another process."""

    get_session_factory.cache_clear()
    get_engine.cache_clear()


async def dispose_database_runtime() -> None:
    """Dispose a cached engine on its owning event loop, then clear its factories."""

    try:
        if get_engine.cache_info().currsize:
            await get_engine().dispose()
    finally:
        reset_database_runtime()


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        try:
            yield session
        finally:
            if session.in_transaction():
                await session.rollback()


async def set_tenant_context(session: AsyncSession, user_id: UUID) -> None:
    """Set the transaction-local user consumed by PostgreSQL RLS policies."""

    await session.execute(
        text("SELECT set_config('app.current_user_id', :user_id, true)"),
        {"user_id": str(user_id)},
    )
