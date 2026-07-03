"""Alembic migration environment.

Supports both online (connected to a live DB) and offline (SQL script) modes.
Uses asyncio for the online mode because the DataPilot engine is async-only.

The DATABASE_URL environment variable overrides the URL in alembic.ini so
that CI pipelines and Kubernetes migrations can inject credentials without
editing config files.

Run migrations::

    # Online — apply to the connected database
    cd backend/infrastructure/persistence/migrations
    alembic upgrade head

    # Offline — generate a SQL script instead
    alembic upgrade head --sql > /tmp/migration.sql
"""
from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# ── Add backend to sys.path so model imports resolve ─────────────────────
# Needed when Alembic is invoked directly (not via pytest/uvicorn which
# set up sys.path already).
_BACKEND_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

# ── Import all ORM models so Alembic can detect schema changes ────────────
from backend.infrastructure.persistence.database import Base  # noqa: E402
from backend.infrastructure.persistence.models.dataset_model         import DatasetModel          # noqa: F401
from backend.infrastructure.persistence.models.session_model         import SessionModel           # noqa: F401
from backend.infrastructure.persistence.models.insight_model         import InsightReportModel     # noqa: F401
from backend.infrastructure.persistence.models.conversation_model    import ConversationModel      # noqa: F401
from backend.infrastructure.persistence.models.message_model         import MessageModel           # noqa: F401
from backend.infrastructure.persistence.models.agent_execution_model import AgentExecutionModel    # noqa: F401

# ── Alembic Config object ─────────────────────────────────────────────────
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override database URL from environment (takes priority over alembic.ini)
database_url = os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Offline mode — generate SQL without connecting
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Generate migration SQL without a live database connection.

    Output is written to stdout when invoked with ``--sql``.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode — apply migrations to a live database
# ---------------------------------------------------------------------------

def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations via a synchronous connection."""
    connectable = create_async_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,   # don't pool connections during migrations
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations using an async engine in an event loop."""
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
