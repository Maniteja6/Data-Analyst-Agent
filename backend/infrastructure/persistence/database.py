"""SQLAlchemy async engine and session factory.

A single async engine and session factory are created at application startup
and shared across all requests. The pattern used here is the recommended
FastAPI + asyncpg approach:

    engine       — one per process; holds the connection pool
    async_session — session factory; each request/task creates one session

Session lifecycle
-----------------
FastAPI routes use ``get_db_session()`` as a dependency; it yields an
``AsyncSession`` scoped to one HTTP request. The session is committed if no
exception is raised, and rolled back otherwise.

Celery tasks use ``get_session()`` as an async context manager directly
(tasks don't use FastAPI's dependency injection).

Connection pool configuration
------------------------------
``pool_size``         — persistent connections kept alive between requests
``max_overflow``      — additional connections beyond pool_size (burst capacity)
``pool_pre_ping``     — test connections on checkout (handles DB restarts)
``pool_recycle``      — refresh connections after N seconds (avoids cloud firewall drops)
``connect_args``      — passed directly to asyncpg; ``server_settings`` sets
                         the Postgres search path and application_name

Usage::

    # FastAPI dependency
    async def my_handler(db: AsyncSession = Depends(get_db_session)):
        repo = PostgresDatasetRepository(db)
        return await repo.get_by_id("abc-123")

    # Celery task / async context manager
    async with get_session() as session:
        repo = PostgresDatasetRepository(session)
        await repo.save(dataset)
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# ORM base class — imported by all model files
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all DataPilot ORM models."""


# ---------------------------------------------------------------------------
# Engine singleton
# ---------------------------------------------------------------------------

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the async engine singleton, creating it on first call.

    Reads connection settings from ``Settings`` so any environment variable
    override is respected (e.g. ``DATABASE_URL`` in tests).
    """
    global _engine, _session_factory
    if _engine is None:
        from backend.config.settings import get_settings
        settings = get_settings()

        _engine = create_async_engine(
            settings.database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_pre_ping=True,          # reconnect after DB restarts
            pool_recycle=3600,           # replace connections after 1 hour
            echo=settings.debug,         # log SQL when debug=True
            connect_args={
                "server_settings": {
                    "application_name": settings.app_name,
                    "search_path":      "public",
                },
            },
        )
        _session_factory = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,      # don't expire objects after commit
            autoflush=False,             # explicit flush control
        )
        logger.info(
            "db_engine_created",
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
        )
    return _engine


# ---------------------------------------------------------------------------
# Session factories
# ---------------------------------------------------------------------------

@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager that provides a scoped database session.

    Commits on normal exit, rolls back on exception.

    Usage (Celery tasks, event handlers)::

        async with get_session() as session:
            repo = PostgresDatasetRepository(session)
            await repo.save(dataset)
    """
    get_engine()   # ensure engine is initialised
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a scoped ``AsyncSession``.

    Commits on success, rolls back on error, and always closes the session.

    Usage::

        @router.get("/datasets/{dataset_id}")
        async def get_dataset(
            dataset_id: str,
            db: AsyncSession = Depends(get_db_session),
        ):
            repo = PostgresDatasetRepository(db)
            return await repo.get_by_id(dataset_id)
    """
    get_engine()
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Lifecycle helpers
# ---------------------------------------------------------------------------

async def health_check() -> bool:
    """Return True when the database is reachable (used by /ready endpoint)."""
    try:
        from sqlalchemy import text
        async with _session_factory() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("db_health_check_failed", error=str(exc))
        return False


async def dispose_engine() -> None:
    """Close all connections and dispose the engine pool.

    Call during application shutdown lifespan to ensure all asyncpg
    connections are cleanly closed before the process exits.
    """
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine         = None
        _session_factory = None
        logger.info("db_engine_disposed")
