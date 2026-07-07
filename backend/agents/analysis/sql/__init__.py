"""SQL agent — NL → validated DuckDB SELECT → formatted result rows.

Pipeline: generate_sql() → validate() → execute_query() → ResultFormatter
Real-time: emits job:progress 55%≤62%; returns vega_data for VegaEmbed.
"""

from backend.agents.analysis.sql.duckdb_executor import execute_query
from backend.agents.analysis.sql.sql_agent import SQLAgent
from backend.agents.analysis.sql.sql_generator import generate_sql
from backend.agents.analysis.sql.sql_validator import SQLValidationError, validate

__all__ = ["SQLAgent", "validate", "SQLValidationError", "generate_sql", "execute_query"]
