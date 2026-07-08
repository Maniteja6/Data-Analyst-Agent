"""LLM-based NL→SQL generator for DuckDB agent queries.

Injects the dataset schema into the prompt so the model generates
syntactically correct DuckDB SQL referencing real column names.
"""

from __future__ import annotations

from typing import Any

import structlog
from backend.infrastructure.llm.model_id_registry import get_model_id

logger = structlog.get_logger(__name__)

_SYSTEM = (
    "You are a DuckDB SQL expert. "
    "The dataset is registered as a view called `dataset`. "
    "Return ONLY the raw SQL query — no markdown, no explanation, no backticks."
)


async def generate_sql(
    question: str,
    schema: dict[str, Any],
    llm_client: Any,  # noqa: ANN401
    row_limit: int = 10_000,
) -> str:
    """Generate a DuckDB SELECT query for the given natural-language question.

    Args:
        question:   The user's natural-language question.
        schema:     Dataset schema dict with a ``columns`` list, each entry
                    having ``name``, ``data_type``, and ``semantic_type``.
        llm_client: Any object implementing ``async complete(prompt, model_id)``.
        row_limit:  Maximum rows to return (injected as a LIMIT hint).

    Returns:
        Raw SQL string (not yet validated — call ``validate()`` before execution).
    """
    columns = schema.get("columns", [])
    schema_lines = "\n".join(
        f"  {c['name']}  {c['data_type']}  -- {c.get('semantic_type', '')}" for c in columns
    )

    # Provide extra date-function hints when datetime columns exist
    date_cols = [c["name"] for c in columns if c.get("semantic_type") in ("date", "datetime")]
    date_hint = ""
    if date_cols:
        date_hint = (
            f"\nDate columns: {date_cols}. "
            "Use date_trunc(), date_diff(), strftime() for date arithmetic."
        )

    prompt = f"""Generate a DuckDB SQL SELECT query to answer this question.

TABLE: dataset
SCHEMA:
{schema_lines}
{date_hint}

QUESTION: {question}

RULES:
- SELECT only. No DDL (CREATE/DROP/ALTER). No DML (INSERT/UPDATE/DELETE).
- Quote all column names with double-quotes: "column_name".
- Add LIMIT {row_limit} if not already present.
- Use DuckDB syntax (not PostgreSQL or SQLite).
- For grouping queries, include all SELECT columns in GROUP BY.
- Prefer readable column aliases: revenue_sum, avg_order_value.

Return ONLY the SQL. No explanation."""

    response = await llm_client.complete(
        prompt=prompt,
        system=_SYSTEM,
        model_id=get_model_id("sql"),
    )

    sql = response.strip().rstrip(";")
    logger.debug("sql_generated", question=question[:80], sql_preview=sql[:120])
    return sql
