"""ColumnStatsWriter — writes per-column profiling statistics to ClickHouse.

Called by the analytics pipeline after the DataProfiler completes. Each
profiling run inserts one row per column into the ``column_statistics``
fact table, building up a time-series of data quality metrics that can
be queried for benchmarking and drift detection.

Architecture:
- Writes are buffered in memory and flushed in one bulk insert to avoid
  per-row ClickHouse round-trips (ClickHouse prefers large batches).
- When ``FEATURE_CLICKHOUSE`` is disabled, all write operations are no-ops
  so the rest of the pipeline proceeds normally.
- Write failures are logged as warnings but do not fail the pipeline —
  ClickHouse is not on the critical path.

Usage::

    from backend.infrastructure.analytics_db.column_stats_writer import ColumnStatsWriter

    writer = ColumnStatsWriter()
    await writer.write_profile(
        dataset_id="abc-123",
        session_id="def-456",
        profile=data_profile,          # DataProfile entity
        project_id="proj-789",         # optional
    )
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from backend.config.feature_flags import flags

logger = structlog.get_logger(__name__)

# Target ClickHouse table
_TABLE = "column_statistics"


class ColumnStatsWriter:
    """Converts a ``DataProfile`` entity into ClickHouse row dicts and bulk-inserts them.

    Designed to be called once per profiling session. Thread-safe (no mutable
    instance state) — a single shared instance is sufficient per worker process.
    """

    def __init__(self, client=None) -> None:
        """
        Args:
            client: Optional ``ClickHouseClient`` instance. When None the
                    singleton from ``get_clickhouse_client()`` is used.
                    Pass a mock in tests.
        """
        self._client = client

    # ── Primary entry point ───────────────────────────────────────────────

    async def write_profile(
        self,
        dataset_id: str,
        session_id: str,
        profile: Any,
        project_id: str = "",
    ) -> int:
        """Write all column statistics from a DataProfile to ClickHouse.

        Args:
            dataset_id: Source dataset UUID.
            session_id: Analysis session UUID.
            profile:    A ``DataProfile`` entity (or any duck-typed object
                        with a ``column_profiles`` list attribute).
            project_id: Optional project UUID — enables project-level benchmarks.

        Returns:
            Number of rows inserted (0 when feature flag is disabled).
        """
        if not flags.clickhouse_enabled:
            logger.debug(
                "clickhouse_write_skipped",
                reason="FEATURE_CLICKHOUSE disabled",
                dataset_id=dataset_id,
            )
            return 0

        column_profiles = getattr(profile, "column_profiles", [])
        if not column_profiles:
            logger.warning(
                "clickhouse_no_columns",
                dataset_id=dataset_id,
                session_id=session_id,
            )
            return 0

        profiled_at = datetime.now(timezone.utc)
        rows = [
            self._build_row(col, dataset_id, session_id, project_id, profiled_at)
            for col in column_profiles
        ]

        try:
            client = self._get_client()
            await client.insert(_TABLE, rows)
            logger.info(
                "clickhouse_profile_written",
                dataset_id=dataset_id,
                session_id=session_id,
                row_count=len(rows),
            )
            return len(rows)
        except Exception as exc:
            # ClickHouse is not on the critical path — log but don't propagate
            logger.warning(
                "clickhouse_write_failed",
                dataset_id=dataset_id,
                error=str(exc),
            )
            return 0

    # ── Incremental / streaming write ─────────────────────────────────────

    async def write_column(
        self,
        column_profile: Any,
        dataset_id: str,
        session_id: str,
        project_id: str = "",
    ) -> None:
        """Write a single column's statistics.

        Used when profiling is done column-by-column (streaming mode for
        very wide datasets). Less efficient than ``write_profile`` because
        it issues one insert per column rather than a bulk insert.
        """
        if not flags.clickhouse_enabled:
            return

        profiled_at = datetime.now(timezone.utc)
        row = self._build_row(column_profile, dataset_id, session_id, project_id, profiled_at)
        try:
            client = self._get_client()
            await client.insert(_TABLE, [row])
        except Exception as exc:
            logger.warning("clickhouse_column_write_failed", error=str(exc))

    # ── Delete ────────────────────────────────────────────────────────────

    async def delete_by_dataset(self, dataset_id: str) -> None:
        """Remove all column statistics for a dataset (called on dataset deletion).

        ClickHouse deletes are asynchronous ALTER TABLE ... DELETE mutations;
        they are scheduled but not immediately applied. This is acceptable for
        GDPR erasure requests — the data will be removed within minutes.
        """
        if not flags.clickhouse_enabled:
            return
        try:
            client = self._get_client()
            await client.command(
                f"ALTER TABLE {_TABLE} DELETE WHERE dataset_id = '{dataset_id}'"
            )
            logger.info("clickhouse_dataset_deleted", dataset_id=dataset_id)
        except Exception as exc:
            logger.warning("clickhouse_delete_failed", dataset_id=dataset_id, error=str(exc))

    # ── Private helpers ───────────────────────────────────────────────────

    def _get_client(self):
        """Return the ClickHouseClient, lazily importing the singleton."""
        if self._client is None:
            from backend.infrastructure.analytics_db.clickhouse_client import get_clickhouse_client
            self._client = get_clickhouse_client()
        return self._client

    @staticmethod
    def _build_row(
        col: Any,
        dataset_id: str,
        session_id: str,
        project_id: str,
        profiled_at: datetime,
    ) -> dict:
        """Convert a ``ColumnProfile`` entity into a ClickHouse row dict.

        Handles both the domain entity form (attribute access) and the plain
        dict form (key access) produced by ``ColumnProfile.to_dict()``.
        """
        def _get(obj, *keys, default=None):
            """Try attribute access then dict access."""
            for key in keys:
                v = getattr(obj, key, None)
                if v is not None:
                    return v
            if isinstance(obj, dict):
                for key in keys:
                    v = obj.get(key)
                    if v is not None:
                        return v
            return default

        # Core identity fields
        column_name  = _get(col, "column_name", "name", default="")
        data_type    = _get(col, "data_type", "dtype", default="unknown")
        semantic_type = _get(col, "semantic_type", default="unknown")
        # SemanticType enum → string
        if hasattr(semantic_type, "value"):
            semantic_type = semantic_type.value

        kind = _get(col, "kind", default="unknown")
        if hasattr(kind, "value"):
            kind = kind.value

        total_rows   = int(_get(col, "total_rows", default=0))
        null_count   = int(_get(col, "null_count", default=0))
        unique_count = int(_get(col, "unique_count", default=0))
        null_rate    = float(_get(col, "null_rate", default=0.0))
        completeness = float(_get(col, "completeness", default=1.0))

        # Numeric statistics from StatisticalSummary VO
        stats = _get(col, "stats")
        if isinstance(stats, dict):
            mean     = stats.get("mean")
            stddev   = stats.get("stddev")
            min_val  = stats.get("min") or stats.get("min_val")
            max_val  = stats.get("max") or stats.get("max_val")
            p25      = stats.get("p25")
            p50      = stats.get("p50")
            p75      = stats.get("p75")
            skewness = stats.get("skewness")
        elif stats is not None:
            mean     = getattr(stats, "mean",     None)
            stddev   = getattr(stats, "stddev",   None)
            min_val  = getattr(stats, "min_val",  None)
            max_val  = getattr(stats, "max_val",  None)
            p25      = getattr(stats, "p25",      None)
            p50      = getattr(stats, "p50",      None)
            p75      = getattr(stats, "p75",      None)
            skewness = getattr(stats, "skewness", None)
        else:
            mean = stddev = min_val = max_val = p25 = p50 = p75 = skewness = None

        is_constant         = int(bool(_get(col, "is_constant",         default=False)))
        is_high_cardinality = int(bool(_get(col, "is_high_cardinality", default=False)))

        return {
            "dataset_id":          dataset_id,
            "session_id":          session_id,
            "project_id":          project_id,
            "column_name":         column_name,
            "profiled_at":         profiled_at,
            "data_type":           str(data_type),
            "semantic_type":       str(semantic_type),
            "kind":                str(kind),
            "total_rows":          total_rows,
            "null_count":          null_count,
            "unique_count":        unique_count,
            "null_rate":           null_rate,
            "completeness":        completeness,
            "mean":                mean,
            "stddev":              stddev,
            "min_val":             min_val,
            "max_val":             max_val,
            "p25":                 p25,
            "p50":                 p50,
            "p75":                 p75,
            "skewness":            skewness,
            "is_constant":         is_constant,
            "is_high_cardinality": is_high_cardinality,
        }
