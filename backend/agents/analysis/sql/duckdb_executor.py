"""DuckDB executor for SQL agent queries.

Uses ``read_auto()`` to load the dataset file directly into DuckDB without
copying it into Postgres first. Supports CSV, Parquet, Excel, and JSON.

All DuckDB calls are synchronous and run in a dedicated thread pool so
they don't block the asyncio event loop.
"""
from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Dedicated thread pool — separate from the S3 and embedding pools
_DUCKDB_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="duckdb_worker")

DEFAULT_ROW_LIMIT = 10_000
DEFAULT_TIMEOUT   = 30    # seconds
MEMORY_LIMIT      = "1GB"


async def execute_query(
    sql: str,
    storage_key: str,
    row_limit: int = DEFAULT_ROW_LIMIT,
    timeout: int   = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Execute a validated SELECT query against the dataset file.

    Args:
        sql:         Pre-validated SELECT statement.
        storage_key: Local file path or S3 URL to the dataset file.
        row_limit:   Maximum rows to return.
        timeout:     Wall-clock timeout in seconds.

    Returns:
        Dict with keys: ``rows``, ``column_names``, ``row_count``,
        ``execution_time_ms``, ``truncated``.
    """
    loop = asyncio.get_event_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(
                _DUCKDB_POOL,
                _run_query,
                sql,
                storage_key,
                row_limit,
            ),
            timeout=timeout,
        )
        return result
    except TimeoutError:
        logger.error(
            "duckdb_timeout",
            timeout=timeout,
            sql_preview=sql[:100],
        )
        return {
            "rows":             [],
            "column_names":     [],
            "row_count":        0,
            "execution_time_ms": timeout * 1000,
            "truncated":        False,
            "error":            f"Query timed out after {timeout}s",
        }
    except Exception as exc:
        logger.error("duckdb_execute_failed", error=str(exc))
        return {
            "rows":             [],
            "column_names":     [],
            "row_count":        0,
            "execution_time_ms": 0,
            "truncated":        False,
            "error":            str(exc),
        }


def _run_query(sql: str, storage_key: str, row_limit: int) -> dict[str, Any]:
    """Synchronous DuckDB query execution (runs in thread pool)."""
    import duckdb

    start = time.monotonic()
    con   = duckdb.connect(database=":memory:")
    try:
        con.execute(f"SET memory_limit='{MEMORY_LIMIT}'")
        con.execute("SET threads=2")

        # Register dataset — read_auto() auto-detects CSV/Parquet/JSON/Excel
        # Use the local storage path when available (avoids S3 latency in dev)
        con.execute(
            f"CREATE VIEW dataset AS SELECT * FROM read_auto('{storage_key}')"
        )

        # Enforce LIMIT on the outer query
        wrapped = f"SELECT * FROM ({sql}) __q LIMIT {row_limit}"
        rel     = con.execute(wrapped)

        columns = [desc[0] for desc in rel.description]
        rows    = rel.fetchall()
        duration = int((time.monotonic() - start) * 1000)

        logger.info(
            "duckdb_query_complete",
            row_count=len(rows),
            duration_ms=duration,
            truncated=len(rows) >= row_limit,
        )
        return {
            "rows":              [dict(zip(columns, row)) for row in rows],
            "column_names":      columns,
            "row_count":         len(rows),
            "execution_time_ms": duration,
            "truncated":         len(rows) >= row_limit,
        }
    finally:
        con.close()


async def describe_table(storage_key: str) -> list[dict]:
    """Return column names and types from the dataset file (schema sniff)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_DUCKDB_POOL, _describe, storage_key)


def _describe(storage_key: str) -> list[dict]:
    import duckdb
    con = duckdb.connect(":memory:")
    try:
        rel = con.execute(
            f"DESCRIBE SELECT * FROM read_auto('{storage_key}') LIMIT 1"
        )
        return [
            {"column_name": row[0], "column_type": row[1]}
            for row in rel.fetchall()
        ]
    finally:
        con.close()
