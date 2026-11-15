"""Async engine/session factory and schema bootstrap."""

from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base


def create_engine(settings: Settings) -> AsyncEngine:
    """Build an async engine appropriate for the configured database URL."""
    kwargs: dict[str, Any] = {"echo": settings.database_echo, "pool_pre_ping": True}
    if settings.is_sqlite:
        kwargs["connect_args"] = {"timeout": 30}
        if ":memory:" in settings.database_url:
            # Keep a single connection alive so the in-memory schema persists.
            kwargs["poolclass"] = StaticPool

    engine = create_async_engine(settings.database_url, **kwargs)

    if settings.is_sqlite:

        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create the session factory used by request-scoped dependencies."""
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def init_models(engine: AsyncEngine) -> None:
    """Create all tables that do not exist yet (idempotent)."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def drop_models(engine: AsyncEngine) -> None:
    """Drop every table (used by tests and maintenance commands)."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
