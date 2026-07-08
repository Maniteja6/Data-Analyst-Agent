"""SchemaAgent — infers column semantic types with real-time Socket.IO progress.

Real-time pipeline:
    1. Read 1000 sample rows via FileReader
    2. Run TypeInferencer on every column (synchronous, < 5ms total)
    3. Emit ``schema:column_classified`` for each deterministic column
    4. Batch-classify ambiguous columns (needs_llm=True) via SemanticClassifier
    5. Build final schema dict and store in AgentContext
    6. Emit ``schema:complete`` with the full column list

Socket.IO events emitted:
    schema:progress         — "Inferring 24 columns…"
    schema:column_classified — per column as it resolves
    schema:complete          — full schema payload on completion

The per-column events allow the frontend to render a live schema table that
fills in column by column rather than waiting for all columns to complete.
This is particularly valuable for wide datasets (50+ columns) where type
inference takes a few seconds.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

import structlog
from backend.agents.base.agent_context import AgentContext
from backend.agents.base.base_agent import BaseAgent
from backend.agents.data.schema.semantic_classifier import SemanticClassifier
from backend.agents.data.schema.type_inferencer import (
    TypeInference,
    infer_all_columns,
)

logger = structlog.get_logger(__name__)

SAMPLE_ROWS = 1_000  # rows to read for type inference


class SchemaAgent(BaseAgent):
    """Infers column semantic types for an uploaded dataset.

    Args:
        llm_client: Async LLM client passed to SemanticClassifier (Haiku).
                    When None, ambiguous columns remain 'unknown'.
    """

    def __init__(self, llm_client: Any = None) -> None:  # noqa: ANN401
        super().__init__("schema")
        self._llm = llm_client
        self._classifier = SemanticClassifier(llm_client)

    async def _execute(self, context: AgentContext, **kwargs: Any) -> dict:  # noqa: ANN401
        """Infer schema for the dataset at context.storage_key.

        Returns:
            Schema dict with ``columns``, ``row_count_sample``, ``column_count``,
            ``has_time_series``, and ``numeric_column_count``.
        """
        sio = context._sio
        dataset_id = context.dataset_id

        # ── Step 1: Load sample rows ──────────────────────────────────────
        from backend.analytics_engine.ingestion.file_reader import FileReader

        await context.push_progress(3, "Loading dataset sample…", step="schema")

        df = await FileReader().read(context.storage_key, sample_rows=SAMPLE_ROWS)

        col_count = len(df.columns) if hasattr(df, "columns") else df.shape[1]
        row_count = len(df) if hasattr(df, "__len__") else df.shape[0]

        await context.push_progress(6, f"Inferring types for {col_count} columns…", step="schema")

        # ── Step 2: TypeInferencer — deterministic, instant ───────────────
        start = time.monotonic()

        inferences: list[TypeInference] = await asyncio.get_event_loop().run_in_executor(
            None,
            infer_all_columns,
            df,
            None,  # emit_progress=None here; we do it below
        )

        # Emit per-column classified events for the deterministic ones
        if sio and dataset_id:
            for inf in inferences:
                if not inf.needs_llm:
                    with contextlib.suppress(Exception):
                        await sio.emit(
                            "schema:column_classified",
                            {
                                "dataset_id": dataset_id,
                                "column_name": inf.column_name,
                                "semantic_type": inf.semantic_type,
                                "confidence": inf.confidence,
                                "source": "rule",
                            },
                            room=f"dataset:{dataset_id}",
                        )

        # ── Step 3: LLM disambiguation — ambiguous columns only ───────────
        ambiguous = [inf for inf in inferences if inf.needs_llm]
        if ambiguous:
            await context.push_progress(
                10,
                f"Classifying {len(ambiguous)} ambiguous columns via AI…",
                step="schema",
            )
            llm_overrides = await self._classifier.classify_batch(
                ambiguous, sio=sio, dataset_id=dataset_id
            )
            # Apply overrides
            for inf in inferences:
                if inf.column_name in llm_overrides:
                    inf.semantic_type = llm_overrides[inf.column_name]
                    inf.needs_llm = False

        elapsed_ms = int((time.monotonic() - start) * 1000)

        # ── Step 4: Build schema dict ─────────────────────────────────────
        columns = [
            {
                "name": inf.column_name,
                "data_type": inf.data_type,
                "semantic_type": inf.semantic_type,
                "confidence": inf.confidence,
                "nullable": inf.null_rate > 0,
                "null_rate": inf.null_rate,
                "unique_count": inf.unique_count,
                "missing_count": int(inf.null_rate * row_count),
                "sample_values": inf.sample_values,
                "is_primary_key": inf.semantic_type == "identifier"
                and inf.unique_count == row_count,
            }
            for inf in inferences
        ]

        has_time_series = any(c["semantic_type"] in ("date", "datetime") for c in columns)
        numeric_col_count = sum(
            1
            for c in columns
            if c["semantic_type"] in ("currency", "numeric_measure", "numeric_count", "percentage")
        )

        schema = {
            "columns": columns,
            "row_count_sample": row_count,
            "column_count": col_count,
            "has_time_series": has_time_series,
            "numeric_column_count": numeric_col_count,
            "ambiguous_count": len(ambiguous),
            "inference_ms": elapsed_ms,
        }

        context.schema = schema

        # ── Step 5: Emit schema:complete ──────────────────────────────────
        if sio and dataset_id:
            with contextlib.suppress(Exception):
                await sio.emit(
                    "schema:complete",
                    {
                        "dataset_id": dataset_id,
                        "column_count": col_count,
                        "has_time_series": has_time_series,
                        "numeric_col_count": numeric_col_count,
                        "columns": columns,
                        "inference_ms": elapsed_ms,
                    },
                    room=f"dataset:{dataset_id}",
                )

        logger.info(
            "schema_agent_complete",
            columns=col_count,
            ambiguous=len(ambiguous),
            has_time_series=has_time_series,
            inference_ms=elapsed_ms,
        )
        return schema
