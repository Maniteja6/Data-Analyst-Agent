"""ClickHouse client — column-store analytics database for DataPilot.

ClickHouse is used for cross-dataset aggregate queries that would be
slow or expensive on PostgreSQL, such as:

- "How does this dataset's completeness compare to our average?"
- "Which columns have the highest anomaly rate across all uploads?"
- "What is the P95 row count for datasets in this project?"

It is NOT the primary metadata store (that's PostgreSQL) and it is NOT
used for the hot read path (that's Redis). It is exclusively for analytical
queries over the ``column_statistics`` fact table populated by
``ColumnStatsWriter`` after each profiling run.

Architecture note: ClickHouse is optional — the ``FEATURE_CLICKHOUSE``
flag must be enabled for any write to occur. When disabled, all writes
are no-ops and read queries fall back to PostgreSQL aggregations.

Usage::

    from backend.infrastructure.analytics_db.clickhouse_client import get_clickhouse_client

    client = await get_clickhouse_client()
    result = await client.query(
        "SELECT avg(completeness_score) FROM column_statistics WHERE project_id = %(pid)s",
        parameters={"pid": "abc-123"},
    )
"""
from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# ClickHouse DDL — column_statistics fact table
# ---------------------------------------------------------------------------
COLUMN_STATISTICS_DDL = """
CREATE TABLE IF NOT EXISTS column_statistics
(
    -- Identity
    id                  UUID          DEFAULT generateUUIDv4(),
    dataset_id          String        NOT NULL,
    session_id          String        NOT NULL,
    project_id          String        DEFAULT '',
    column_name         String        NOT NULL,
    profiled_at         DateTime64(3) NOT NULL,

    -- Type metadata
    data_type           String        NOT NULL,
    semantic_type       String        NOT NULL DEFAULT 'unknown',
    kind                String        NOT NULL DEFAULT 'unknown',

    -- Completeness
    total_rows          UInt64        NOT NULL,
    null_count          UInt64        NOT NULL DEFAULT 0,
    unique_count        UInt64        NOT NULL DEFAULT 0,
    null_rate           Float32       NOT NULL DEFAULT 0.0,
    completeness        Float32       NOT NULL DEFAULT 1.0,

    -- Numeric statistics (nullable for non-numeric columns)
    mean                Nullable(Float64),
    stddev              Nullable(Float64),
    min_val             Nullable(Float64),
    max_val             Nullable(Float64),
    p25                 Nullable(Float64),
    p50                 Nullable(Float64),
    p75                 Nullable(Float64),
    skewness            Nullable(Float64),

    -- Quality flags
    is_constant         UInt8         NOT NULL DEFAULT 0,
    is_high_cardinality UInt8         NOT NULL DEFAULT 0
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(profiled_at)
ORDER BY (dataset_id, column_name, profiled_at)
TTL profiled_at + INTERVAL 1 YEAR
SETTINGS index_granularity = 8192;
"""


class ClickHouseClient:
    """Async wrapper around the ClickHouse HTTP/native client.

    Uses the ``clickhouse-connect`` library which supports both asyncio
    (via ``asyncclient``) and sync access. The async client is preferred
    to avoid blocking the FastAPI event loop during bulk inserts.

    Connection is established lazily on first use and is a singleton per
    worker process (the EKS pod). No connection pool is needed because
    ClickHouse's HTTP endpoint is stateless.
    """

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        secure: bool = False,
    ) -> None:
        self._host     = host
        self._port     = port
        self._database = database
        self._username = username
        self._password = password
        self._secure   = secure
        self._client   = None   # lazily initialised

    # ── Connection ────────────────────────────────────────────────────────

    async def _get_client(self):
        """Return the async ClickHouse client, creating it on first call."""
        if self._client is None:
            try:
                import clickhouse_connect
                self._client = await clickhouse_connect.get_async_client(
                    host=self._host,
                    port=self._port,
                    database=self._database,
                    username=self._username,
                    password=self._password,
                    secure=self._secure,
                )
                logger.info(
                    "clickhouse_connected",
                    host=self._host,
                    database=self._database,
                )
            except ImportError:
                raise RuntimeError(
                    "clickhouse-connect is not installed. "
                    "Add it to pyproject.toml or disable FEATURE_CLICKHOUSE."
                )
            except Exception as exc:
                logger.error("clickhouse_connection_failed", error=str(exc))
                raise
        return self._client

    async def ping(self) -> bool:
        """Return True if ClickHouse is reachable."""
        try:
            client = await self._get_client()
            result = await client.query("SELECT 1")
            return bool(result.result_rows)
        except Exception as exc:
            logger.warning("clickhouse_ping_failed", error=str(exc))
            return False

    async def close(self) -> None:
        """Close the ClickHouse connection."""
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass
            finally:
                self._client = None

    # ── DDL ───────────────────────────────────────────────────────────────

    async def ensure_schema(self) -> None:
        """Create the column_statistics table if it does not exist.

        Called once at application startup via the lifespan handler,
        only when ``FEATURE_CLICKHOUSE`` is enabled.
        """
        client = await self._get_client()
        await client.command(COLUMN_STATISTICS_DDL)
        logger.info("clickhouse_schema_ensured", table="column_statistics")

    # ── Read ──────────────────────────────────────────────────────────────

    async def query(
        self,
        sql: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict]:
        """Execute a SELECT query and return rows as a list of dicts.

        Args:
            sql:        ClickHouse SQL SELECT statement.
            parameters: Named query parameters (``%(key)s`` placeholders).

        Returns:
            List of row dicts where keys are column names.

        Example::

            rows = await client.query(
                "SELECT column_name, avg(null_rate) AS avg_null_rate "
                "FROM column_statistics "
                "WHERE dataset_id = %(did)s "
                "GROUP BY column_name ORDER BY avg_null_rate DESC",
                parameters={"did": dataset_id},
            )
        """
        ch_client = await self._get_client()
        result    = await ch_client.query(sql, parameters=parameters or {})
        columns   = result.column_names
        return [dict(zip(columns, row)) for row in result.result_rows]

    async def query_single(
        self,
        sql: str,
        parameters: dict[str, Any] | None = None,
    ) -> dict | None:
        """Execute a query expected to return a single row.

        Returns the first row as a dict, or None if the result is empty.
        """
        rows = await self.query(sql, parameters)
        return rows[0] if rows else None

    # ── Write ─────────────────────────────────────────────────────────────

    async def insert(
        self,
        table: str,
        rows: list[dict[str, Any]],
        column_names: list[str] | None = None,
    ) -> None:
        """Bulk-insert rows into a ClickHouse table.

        Args:
            table:        Target table name (must exist).
            rows:         List of row dicts. All dicts must have the same keys.
            column_names: Explicit column list. If None, inferred from the
                          first row's keys.

        Raises:
            ValueError: When ``rows`` is empty.
        """
        if not rows:
            raise ValueError("Cannot insert empty rows list")

        cols = column_names or list(rows[0].keys())
        data = [[row.get(col) for col in cols] for row in rows]

        ch_client = await self._get_client()
        await ch_client.insert(table, data, column_names=cols)
        logger.info(
            "clickhouse_insert",
            table=table,
            row_count=len(rows),
        )

    async def command(self, sql: str) -> None:
        """Execute a DDL or non-SELECT command (CREATE, ALTER, TRUNCATE, etc.)."""
        ch_client = await self._get_client()
        await ch_client.command(sql)

    # ── Analytics helpers ─────────────────────────────────────────────────

    async def get_dataset_stats_summary(self, dataset_id: str) -> dict:
        """Return a high-level quality summary for one dataset.

        Returns:
            Dict with keys: ``avg_completeness``, ``avg_null_rate``,
            ``column_count``, ``numeric_column_count``.
        """
        result = await self.query_single(
            """
            SELECT
                round(avg(completeness), 4)  AS avg_completeness,
                round(avg(null_rate),    4)  AS avg_null_rate,
                count()                       AS column_count,
                countIf(kind = 'numeric')     AS numeric_column_count
            FROM column_statistics
            WHERE dataset_id = %(did)s
            """,
            parameters={"did": dataset_id},
        )
        return result or {}

    async def get_project_completeness_benchmark(self, project_id: str) -> dict:
        """Return average completeness scores across all datasets in a project.

        Used to contextualise a single dataset's completeness against the
        project baseline ("This dataset is 12% below your project average").
        """
        result = await self.query_single(
            """
            SELECT
                round(avg(completeness), 4) AS project_avg_completeness,
                round(min(completeness), 4) AS project_min_completeness,
                round(max(completeness), 4) AS project_max_completeness,
                count(DISTINCT dataset_id)   AS dataset_count
            FROM column_statistics
            WHERE project_id = %(pid)s
            """,
            parameters={"pid": project_id},
        )
        return result or {}

    async def get_high_null_columns(
        self, dataset_id: str, threshold: float = 0.20
    ) -> list[dict]:
        """Return columns with null_rate above the threshold.

        Used by the DataQualityPage to surface columns needing attention.
        """
        return await self.query(
            """
            SELECT column_name, null_rate, semantic_type, unique_count
            FROM column_statistics
            WHERE dataset_id = %(did)s
              AND null_rate   > %(threshold)s
            ORDER BY null_rate DESC
            """,
            parameters={"did": dataset_id, "threshold": threshold},
        )


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_clickhouse_client() -> ClickHouseClient:
    """Return the cached ClickHouseClient singleton.

    Configuration is read from ``Settings`` so any env-var override
    (e.g. in tests) is respected as long as ``get_settings.cache_clear()``
    is called beforehand.

    Call ``get_clickhouse_client.cache_clear()`` in tests to reset.
    """
    from backend.config.settings import get_settings
    s = get_settings()
    return ClickHouseClient(
        host=s.clickhouse_host,
        port=s.clickhouse_port,
        database=s.clickhouse_db,
        username=s.clickhouse_user,
        password=s.clickhouse_password,
        secure=s.clickhouse_secure,
    )
