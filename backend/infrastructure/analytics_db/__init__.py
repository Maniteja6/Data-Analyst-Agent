"""ClickHouse analytics DB — column-level statistics (optional feature).

Enabled when FEATURE_CLICKHOUSE=true.
ClickHouseClient:   execute(), ensure_schema(), ping().
ColumnStatsWriter:  write_profile(dataset_id, profile) → one row per column.
                    Called non-blocking via asyncio.ensure_future() after profiling.
"""

from backend.infrastructure.analytics_db.clickhouse_client import ClickHouseClient
from backend.infrastructure.analytics_db.column_stats_writer import ColumnStatsWriter

__all__ = ["ClickHouseClient", "ColumnStatsWriter"]
