"""MLAgent — runs AutoML on the dataset and narrates the results.

Included in the execution plan only when the dataset has ≥ 5 numeric
columns (gated by the PlannerAgent via has_enough_numeric_columns condition).

Pipeline:
    1. Auto-select target column (first currency or numeric_measure)
    2. Load up to 50k rows
    3. Run AutoML (RandomForest + 3-fold CV)
    4. Log to MLflow (optional)
    5. Generate LLM narrative
    6. Return structured result
"""
from __future__ import annotations

from typing import Any

import structlog
from backend.agents.analysis.ml.auto_ml_pipeline import run_automl
from backend.agents.analysis.ml.model_registry import log_model
from backend.agents.base.agent_context import AgentContext
from backend.agents.base.base_agent import BaseAgent

logger = structlog.get_logger(__name__)

MAX_ROWS = 50_000


class MLAgent(BaseAgent):
    """Runs scikit-learn AutoML and returns structured results + narrative."""

    def __init__(self, llm_client: Any = None) -> None:
        super().__init__("ml")
        self._llm = llm_client

    async def _execute(self, context: AgentContext, **kwargs: Any) -> dict:
        schema = context.schema or {}
        cols   = schema.get("columns", [])

        # ── Auto-select target column ────────────────────────────────────
        priority = {"currency": 0, "numeric_measure": 1, "numeric_count": 2}
        candidates = sorted(
            [c for c in cols if c.get("semantic_type") in priority],
            key=lambda c: priority.get(c["semantic_type"], 99),
        )
        if not candidates:
            return {
                "skipped": True,
                "reason":  "No suitable numeric target column found for ML",
            }

        target_col = candidates[0]["name"]

        # ── Load dataset ──────────────────────────────────────────────────
        from backend.analytics_engine.ingestion.file_reader import FileReader
        df = await FileReader().read(context.storage_key, sample_rows=MAX_ROWS)

        logger.info("ml_agent_starting", target=target_col, schema_cols=len(cols))

        # ── Run AutoML ────────────────────────────────────────────────────
        result = await run_automl(df, target_col, schema)

        if result.get("error"):
            logger.warning("ml_agent_failed", error=result["error"])
            return {
                "skipped": False,
                "error":   result["error"],
            }

        # ── Log to MLflow (non-blocking, optional) ────────────────────────
        log_model(result)

        # ── Generate narrative ────────────────────────────────────────────
        result["narration"] = await self._generate_narration(result)

        logger.info(
            "ml_agent_complete",
            task=result["task"],
            target=target_col,
            cv_score=result.get("cv_score_mean"),
        )
        return result

    async def _generate_narration(self, result: dict) -> str:
        """Write a 3-sentence executive summary of the ML results."""
        if not self._llm:
            scoring_label = "R²" if result.get("scoring") == "r2" else "accuracy"
            return (
                f"A {result.get('model_type', 'ML')} {result.get('task')} model "
                f"was trained to predict {result.get('target')} using "
                f"{result.get('feature_count', 0)} features. "
                f"3-fold cross-validated {scoring_label}: "
                f"{result.get('cv_score_mean', 0):.3f} "
                f"(±{result.get('cv_score_std', 0):.3f}). "
                f"Top feature: {next(iter(result.get('feature_importances', {}) or {}), 'N/A')}."
            )
        try:
            from backend.infrastructure.llm.model_id_registry import get_model_id
            top_features = list((result.get("feature_importances") or {}).keys())[:3]
            prompt = (
                f"Write 3 sentences for a business executive summarising "
                f"these ML results:\n"
                f"Task: {result.get('task')} (predicting {result.get('target')})\n"
                f"Model: {result.get('model_type')} with "
                f"{result.get('cv_score_mean', 0):.3f} cross-validated "
                f"{result.get('scoring')} score\n"
                f"Top 3 predictive features: {top_features}\n"
                "Be specific. Quantify impact where possible. No jargon."
            )
            return await self._llm.complete(
                prompt=prompt, model_id=get_model_id("planner")
            )
        except Exception:
            return f"AutoML completed for target: {result.get('target')}."
