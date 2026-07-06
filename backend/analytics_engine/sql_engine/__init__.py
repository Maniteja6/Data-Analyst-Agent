"""DuckDB SQL engine — connection manager, query builder, result formatter."""
"""SQL engine — safe DuckDB execution for NL→SQL agent queries.

DuckDBManager:   async context manager; registers DataFrame as DuckDB view;
                 dedicated ThreadPoolExecutor separate from S3/embedding pools.
QueryBuilder:    constructs validated SELECT-only DuckDB queries.
ResultFormatter: to_markdown_table(), to_vega_data(), summarise(), to_json().
"""
from backend.analytics_engine.sql_engine.duckdb_manager  import DuckDBManager
from backend.analytics_engine.sql_engine.query_builder   import QueryBuilder
from backend.analytics_engine.sql_engine.result_formatter import ResultFormatter

__all__ = ["DuckDBManager", "QueryBuilder", "ResultFormatter"]
