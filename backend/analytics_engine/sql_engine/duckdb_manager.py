"""DuckDBManager — manages per-request DuckDB connections for in-process SQL."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog

from backend.config.settings import get_settings

logger = structlog.get_logger(__name__)


class DuckDBManager:
    """Manages ephemeral in-process DuckDB connections.

    DuckDB is used for the SQL Agent's ad-hoc queries over uploaded datasets.
    Each analysis session gets its own in-memory connection so there is no
    shared state between concurrent sessions.

    The dataset DataFrame is registered as a virtual table so the SQL Agent
    can query it with standard SELECT statements.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._memory_limit = settings.duckdb_memory_limit
        self._threads      = settings.duckdb_threads

    @asynccontextmanager
    async def session(self, df=None, table_name: str = "df") -> AsyncGenerator:
        """Async context manager that yields a DuckDB connection with the DataFrame registered.

        Args:
            df:         DataFrame to register as a queryable table. When None,
                        the connection is returned without a pre-registered table.
            table_name: SQL table name (default: ``df``).

        Usage::

            async with manager.session(df=clean_df, table_name="sales") as conn:
                result = await conn.execute("SELECT SUM(revenue) FROM sales").fetchall()
        """
        loop = asyncio.get_event_loop()
        conn = await loop.run_in_executor(None, self._create_connection)
        try:
            if df is not None:
                await loop.run_in_executor(None, lambda: conn.register(table_name, df))
                logger.debug("duckdb_table_registered", table=table_name, rows=len(df))
            yield conn
        finally:
            await loop.run_in_executor(None, conn.close)

    def _create_connection(self):
        import duckdb
        conn = duckdb.connect(database=":memory:")
        conn.execute(f"SET memory_limit='{self._memory_limit}'")
        conn.execute(f"SET threads={self._threads}")
        return conn

    async def execute_query(
        self,
        sql: str,
        df=None,
        table_name: str = "df",
        row_limit: int | None = None,
    ) -> list[dict]:
        """Execute a SQL query and return rows as a list of dicts.

        Args:
            sql:        SELECT statement to execute.
            df:         DataFrame to register before querying.
            table_name: Table name used in the SQL.
            row_limit:  Maximum rows to return.

        Returns:
            List of row dicts where keys are column names.
        """
        if row_limit and "LIMIT" not in sql.upper():
            sql = sql.rstrip(";") + f" LIMIT {row_limit}"

        async with self.session(df, table_name) as conn:
            loop   = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._run_query(conn, sql),
            )
            return result

    @staticmethod
    def _run_query(conn, sql: str) -> list[dict]:
        rel     = conn.execute(sql)
        columns = [desc[0] for desc in rel.description]
        rows    = rel.fetchall()
        return [dict(zip(columns, row)) for row in rows]
