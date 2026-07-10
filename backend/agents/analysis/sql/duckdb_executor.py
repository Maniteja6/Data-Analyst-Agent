"""DuckDB executor for SQL agent queries.

Dispatches to the correct DuckDB table function (``read_csv_auto``,
``read_parquet``, ``read_json_auto``, or ``read_xlsx``) based on the dataset
file's extension, mirroring ``analytics_engine.ingestion.format_detector``.
DuckDB has no single function that auto-detects across all of these formats.

All DuckDB calls are synchronous and run in a dedicated thread pool so
they don't block the asyncio event loop.
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Dedicated thread pool — separate from the S3 and embedding pools
_DUCKDB_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="duckdb_worker")

DEFAULT_ROW_LIMIT = 10_000
DEFAULT_TIMEOUT = 30  # seconds
MEMORY_LIMIT = "1GB"

# Mirrors analytics_engine.ingestion.format_detector.EXTENSION_FORMAT_MAP —
# DuckDB table function to use per file extension.
_EXTENSION_READ_FUNCTION = {
    ".csv": "read_csv_auto",
    ".tsv": "read_csv_auto",
    ".txt": "read_csv_auto",
    ".parquet": "read_parquet",
    ".pq": "read_parquet",
    ".json": "read_json_auto",
    ".jsonl": "read_json_auto",
    ".ndjson": "read_json_auto",
    ".xlsx": "read_xlsx",  # requires the DuckDB "excel" community extension
    ".xls": "read_xlsx",
    ".xlsm": "read_xlsx",
}


def _read_function_for(storage_key: str) -> str:
    """Return the DuckDB table function name for a dataset file's extension."""
    ext = Path(storage_key).suffix.lower()
    try:
        return _EXTENSION_READ_FUNCTION[ext]
    except KeyError:
        raise ValueError(
            f"Unsupported dataset file extension {ext!r} for '{storage_key}'."
        ) from None


def _escape_literal(value: str) -> str:
    """Escape a value for safe embedding as a single-quoted SQL string literal.

    Used only where DuckDB can't bind a prepared-statement parameter (e.g.
    inside ``CREATE VIEW``); everywhere else, prefer real parameter binding.
    """
    return value.replace("'", "''")


async def execute_query(
    sql: str,
    storage_key: str,
    row_limit: int = DEFAULT_ROW_LIMIT,
    timeout: int = DEFAULT_TIMEOUT,
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
            "rows": [],
            "column_names": [],
            "row_count": 0,
            "execution_time_ms": timeout * 1000,
            "truncated": False,
            "error": f"Query timed out after {timeout}s",
        }
    except Exception as exc:
        logger.error("duckdb_execute_failed", error=str(exc))
        return {
            "rows": [],
            "column_names": [],
            "row_count": 0,
            "execution_time_ms": 0,
            "truncated": False,
            "error": str(exc),
        }


def _run_query(sql: str, storage_key: str, row_limit: int) -> dict[str, Any]:
    """Synchronous DuckDB query execution (runs in thread pool)."""
    import duckdb

    start = time.monotonic()
    con = duckdb.connect(database=":memory:")
    try:
        con.execute(f"SET memory_limit='{MEMORY_LIMIT}'")
        con.execute("SET threads=2")

        # Register dataset via the extension-appropriate DuckDB reader.
        # Use the local storage path when available (avoids S3 latency in dev)
        # DuckDB DDL (CREATE VIEW) can't take prepared-statement parameters, so
        # the path is escaped as a SQL string literal instead of parameter-bound.
        read_fn = _read_function_for(storage_key)
        con.execute(
            f"CREATE VIEW dataset AS SELECT * FROM {read_fn}('{_escape_literal(storage_key)}')"  # noqa: S608  # nosec B608
        )

        # `sql` is validated by sql_validator.validate() before it ever reaches
        # this function (SELECT-only whitelist, no comments/semicolons/DDL) —
        # DuckDB has no way to bind an entire subquery as a parameter, so this
        # relies on that upstream validation rather than parameter binding.
        # row_limit is coerced to int so it can't smuggle extra SQL either.
        wrapped = f"SELECT * FROM ({sql}) __q LIMIT {int(row_limit)}"  # noqa: S608  # nosec B608
        rel = con.execute(wrapped)

        columns = [desc[0] for desc in rel.description]
        rows = rel.fetchall()
        duration = int((time.monotonic() - start) * 1000)

        logger.info(
            "duckdb_query_complete",
            row_count=len(rows),
            duration_ms=duration,
            truncated=len(rows) >= row_limit,
        )
        return {
            "rows": [dict(zip(columns, row, strict=False)) for row in rows],
            "column_names": columns,
            "row_count": len(rows),
            "execution_time_ms": duration,
            "truncated": len(rows) >= row_limit,
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
        # read_fn comes only from the fixed _EXTENSION_READ_FUNCTION lookup table,
        # never from storage_key text directly — not an injection vector.
        read_fn = _read_function_for(storage_key)
        rel = con.execute(
            f"DESCRIBE SELECT * FROM {read_fn}(?) LIMIT 1",  # noqa: S608  # nosec B608
            [storage_key],
        )
        return [{"column_name": row[0], "column_type": row[1]} for row in rel.fetchall()]
    finally:
        con.close()
