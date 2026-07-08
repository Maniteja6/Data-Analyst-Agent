"""Whitelist-based SQL safety validator for DuckDB agent queries.

Prevents SQL injection, DDL execution, and dangerous DuckDB-specific
commands from reaching the database engine.

Usage::
    from backend.agents.analysis.sql.sql_validator import validate, SQLValidationError

    try:
        validate(generated_sql)
    except SQLValidationError as exc:
        logger.warning("sql_rejected", reason=str(exc))
"""

from __future__ import annotations

import re


class SQLValidationError(ValueError):
    """Raised when generated SQL fails safety validation."""


# Keywords that must never appear in agent-generated SQL
BLOCKED_KEYWORDS: frozenset[str] = frozenset(
    {
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "CREATE",
        "ALTER",
        "TRUNCATE",
        "EXEC",
        "EXECUTE",
        "CALL",
        "GRANT",
        "REVOKE",
        "COPY",
        "ATTACH",
        "DETACH",
        "PRAGMA",
        "VACUUM",
        "INSTALL",
        "LOAD",
        "EXPORT",
        "IMPORT",
        "CHECKPOINT",
        "FORCE",
        "SET",
        "RESET",
    }
)

# DuckDB-specific functions that can read/write the filesystem
BLOCKED_FUNCTIONS: frozenset[str] = frozenset(
    {
        "READ_CSV",
        "READ_PARQUET",
        "READ_JSON",
        "READ_TEXT",
        "WRITE_CSV",
        "WRITE_PARQUET",
        "GLOB",
        "PARQUET_SCHEMA",
        "DUCKDB_SETTINGS",
        "DUCKDB_FUNCTIONS",
    }
)


def validate(sql: str) -> str:
    """Validate and return cleaned SQL, or raise SQLValidationError.

    Args:
        sql: Raw SQL string from the LLM or QueryBuilder.

    Returns:
        The cleaned SQL string (stripped, semicolons removed).

    Raises:
        SQLValidationError: When the SQL fails any safety check.
    """
    if not sql or not sql.strip():
        raise SQLValidationError("Empty SQL string received.")

    # Strip markdown fences if the LLM wrapped output
    cleaned = sql.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(line for line in lines if not line.startswith("```")).strip()

    cleaned = cleaned.rstrip(";").strip()
    norm = cleaned.upper()

    # Must start with SELECT
    if not norm.lstrip().startswith("SELECT"):
        raise SQLValidationError(f"Only SELECT statements are permitted. Got: {cleaned[:60]!r}")

    # Block dangerous DDL / DML keywords
    for kw in BLOCKED_KEYWORDS:
        if re.search(rf"\b{kw}\b", norm):
            raise SQLValidationError(f"Blocked SQL keyword detected: {kw!r}")

    # Block dangerous DuckDB file-access functions
    for fn in BLOCKED_FUNCTIONS:
        if re.search(rf"\b{fn}\s*\(", norm):
            raise SQLValidationError(f"Blocked DuckDB function detected: {fn!r}")

    # Block SQL comments (injection vector)
    if "--" in cleaned or "/*" in cleaned:
        raise SQLValidationError("SQL comments are not permitted in agent-generated queries.")

    # Block multiple statements (semicolon splitting)
    if ";" in cleaned:
        raise SQLValidationError("Multiple SQL statements are not permitted.")

    return cleaned


def is_safe(sql: str) -> bool:
    """Return True when the SQL passes all safety checks, False otherwise."""
    try:
        validate(sql)
        return True
    except SQLValidationError:
        return False
