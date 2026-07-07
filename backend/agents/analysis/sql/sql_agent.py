"""SQLAgent — orchestrates NL → SQL → DuckDB → formatted result.

The SQLAgent is invoked by the analysis fan-out node and during chat
queries when ``IntentClassification.requires_sql`` is True.

Pipeline:
    1. ``sql_generator.generate_sql()``  — NL → raw SQL via Claude Haiku
    2. ``sql_validator.validate()``      — safety check (SELECT-only whitelist)
    3. ``duckdb_executor.execute_query()`` — run in thread pool
    4. ``result_formatter.to_markdown_table()`` — human-readable output
    5. Return structured result dict for InsightAgent consumption

Retry strategy:
    If the generated SQL fails validation or DuckDB execution, the agent
    retries once with an error-correction prompt telling the model what
    went wrong. BaseAgent provides outer retry for transient errors.
"""
from __future__ import annotations

from typing import Any

import structlog
from backend.agents.analysis.sql.duckdb_executor import execute_query
from backend.agents.analysis.sql.sql_generator import generate_sql
from backend.agents.analysis.sql.sql_validator import SQLValidationError, validate
from backend.agents.base.agent_context import AgentContext
from backend.agents.base.base_agent import BaseAgent
from backend.analytics_engine.sql_engine.result_formatter import ResultFormatter

logger = structlog.get_logger(__name__)


class SQLAgent(BaseAgent):
    """NL→SQL→DuckDB agent for structured data queries."""

    ROW_LIMIT = 10_000
    TIMEOUT   = 30

    def __init__(self, llm_client: Any) -> None:
        super().__init__("sql")
        self._llm       = llm_client
        self._formatter = ResultFormatter()

    async def _execute(
        self,
        context: AgentContext,
        question: str = "",
        **kwargs: Any,
    ) -> dict:
        """Generate SQL, validate, execute, and return formatted results.

        Args:
            context:  Shared pipeline state (schema, storage_key).
            question: Natural-language question from the user or PlannerAgent.

        Returns:
            Dict with keys: question, generated_sql, rows, column_names,
            row_count, execution_time_ms, markdown_table, summary, error.
        """
        schema       = context.schema or {}
        storage_key  = context.storage_key

        # ── Step 1: Generate SQL ──────────────────────────────────────────
        raw_sql = await generate_sql(question, schema, self._llm, self.ROW_LIMIT)

        # ── Step 2: Validate ──────────────────────────────────────────────
        try:
            safe_sql = validate(raw_sql)
        except SQLValidationError as exc:
            logger.warning("sql_validation_failed", error=str(exc), sql=raw_sql[:200])
            # One correction attempt
            safe_sql = await self._correction_attempt(question, raw_sql, str(exc), schema)

        # ── Step 3: Execute ───────────────────────────────────────────────
        exec_result = await execute_query(safe_sql, storage_key, self.ROW_LIMIT, self.TIMEOUT)

        if exec_result.get("error"):
            logger.warning(
                "sql_execution_failed",
                error=exec_result["error"],
                sql=safe_sql[:200],
            )
            return {
                "question":     question,
                "generated_sql": safe_sql,
                "rows":         [],
                "column_names": [],
                "row_count":    0,
                "markdown_table": "",
                "summary":      f"Query failed: {exec_result['error']}",
                "error":        exec_result["error"],
            }

        # ── Step 4: Format ────────────────────────────────────────────────
        rows           = exec_result["rows"]
        markdown_table = self._formatter.to_markdown_table(rows, max_rows=50)
        summary        = self._formatter.summarise(rows)

        logger.info(
            "sql_agent_complete",
            question=question[:80],
            row_count=exec_result["row_count"],
            duration_ms=exec_result["execution_time_ms"],
        )

        return {
            "question":          question,
            "generated_sql":     safe_sql,
            "rows":              rows,
            "column_names":      exec_result["column_names"],
            "row_count":         exec_result["row_count"],
            "execution_time_ms": exec_result["execution_time_ms"],
            "truncated":         exec_result.get("truncated", False),
            "markdown_table":    markdown_table,
            "summary":           summary,
            "vega_data":         self._formatter.to_vega_data(rows[:200]),
            "error":             None,
        }

    async def _correction_attempt(
        self,
        question: str,
        bad_sql: str,
        error: str,
        schema: dict,
    ) -> str:
        """Ask the LLM to fix its own SQL given the error message."""
        from backend.infrastructure.llm.model_id_registry import get_model_id
        correction_prompt = (
            f"The following SQL query failed validation:\n\n{bad_sql}\n\n"
            f"Error: {error}\n\n"
            f"Fix the SQL to answer this question: {question}\n"
            "Return ONLY the corrected SQL. No explanation."
        )
        corrected = await self._llm.complete(
            prompt=correction_prompt,
            model_id=get_model_id("sql"),
        )
        return validate(corrected.strip().rstrip(";"))
