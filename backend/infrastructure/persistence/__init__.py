"""Persistence layer — SQLAlchemy engine, ORM models, migrations, repositories."""
"""Persistence — async SQLAlchemy + Postgres + Alembic.

database.py:   async engine singleton; get_session() context manager;
               get_db_session() FastAPI Depends; dispose_engine() for lifespan.
models/:       6 ORM models with JSONB columns and partial indexes.
repositories/: 4 async Postgres repositories.
migrations/:   Alembic env.py + 3 version scripts.
"""
from backend.infrastructure.persistence.database import get_session, get_db_session

__all__ = ["get_session", "get_db_session"]
