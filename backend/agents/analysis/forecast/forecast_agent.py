"""ForecastAgent — detects time series and runs parallel forecasting models.

Runs Prophet and AutoARIMA concurrently with asyncio.gather, then picks
the best result via model_selector. Falls back to XGBoost if both fail.

The agent is only included in the execution plan when
``has_time_series_condition`` returns True (i.e. the dataset has at
least one datetime column and ≥ 30 rows).
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog

from backend.agents.base.base_agent import BaseAgent
from backend.agents.base.agent_context import AgentContext
from backend.agents.analysis.forecast.ts_detector import (
    detect_time_series_columns,
    detect_numeric_targets,
    is_forecasting_viable,
)
from backend.agents.analysis.forecast.prophet_runner    import run_prophet
from backend.agents.analysis.forecast.arima_runner      import run_arima
from backend.agents.analysis.forecast.xgboost_forecaster import run_xgboost
from backend.agents.analysis.forecast.model_selector    import select_best_model

logger = structlog.get_logger(__name__)


class ForecastAgent(BaseAgent):
    """Time-series forecasting agent.

    Runs Prophet + AutoARIMA in parallel and selects the best model.
    Falls through to XGBoost when both primary models fail.

    Args:
        llm_client: Optional LLM client for narrative generation.
        horizon:    Forecast horizon in days (default: 30).
    """

    def __init__(self, llm_client=None, horizon: int = 30) -> None:
        super().__init__("forecast")
        self._llm     = llm_client
        self._horizon = horizon

    async def _execute(self, context: AgentContext, **kwargs: Any) -> dict:
        schema = context.schema or {}

        # ── Check viability ───────────────────────────────────────────────
        check = is_forecasting_viable(schema)
        if not check["viable"]:
            logger.info("forecast_skipped", reason=check["reason"])
            return {"forecasts": [], "skipped": True, "reason": check["reason"]}

        date_cols    = check["date_cols"]
        numeric_cols = check["target_cols"]
        date_col     = date_cols[0]
        target_col   = numeric_cols[0]

        # ── Load dataset ──────────────────────────────────────────────────
        from backend.analytics_engine.ingestion.file_reader import FileReader
        df = await FileReader().read(context.storage_key)

        logger.info(
            "forecast_starting",
            date_col=date_col,
            target_col=target_col,
            horizon=self._horizon,
        )

        # ── Run Prophet + ARIMA concurrently ──────────────────────────────
        prophet_task = asyncio.create_task(
            run_prophet(df, date_col, target_col, self._horizon)
        )
        arima_task   = asyncio.create_task(
            run_arima(df, date_col, target_col, self._horizon)
        )
        prophet_result, arima_result = await asyncio.gather(
            prophet_task, arima_task, return_exceptions=False
        )

        # ── Select best model ─────────────────────────────────────────────
        best = select_best_model(prophet_result, arima_result)

        # ── XGBoost fallback ─────────────────────────────────────────────
        if "error" in best:
            logger.info("forecast_falling_back_to_xgboost")
            best = await run_xgboost(df, date_col, target_col, self._horizon)

        # ── Generate LLM narrative ────────────────────────────────────────
        narration = await self._generate_narration(best, target_col, date_col)

        result = {
            "forecasts": [
                {
                    "target_column":    target_col,
                    "date_column":      date_col,
                    "horizon_label":    f"{self._horizon} days",
                    "model_name":       best.get("model", "Unknown"),
                    "predictions":      best.get("predictions", []),
                    "trend_direction":  best.get("trend_direction", "unknown"),
                    "training_rows":    best.get("training_rows", 0),
                    "narration":        narration,
                }
            ],
            "models_attempted": ["Prophet", "AutoARIMA"],
            "best_model":       best.get("model"),
        }

        logger.info(
            "forecast_complete",
            model=best.get("model"),
            predictions=len(best.get("predictions", [])),
        )
        return result

    async def _generate_narration(
        self,
        model_result: dict,
        target_col: str,
        date_col: str,
    ) -> str:
        """Generate a 2-sentence business narrative for the forecast."""
        if not self._llm or "error" in model_result:
            trend = model_result.get("trend_direction", "unknown")
            preds = model_result.get("predictions", [])
            n     = len(preds)
            return (
                f"Forecast generated using {model_result.get('model', 'ML')} "
                f"for {target_col} over the next {n} days. "
                f"The trend appears to be {trend}."
            )
        try:
            from backend.infrastructure.llm.model_id_registry import get_model_id
            predictions = model_result.get("predictions", [])
            sample = predictions[:3] if predictions else []
            prompt = (
                f"Write 2 sentences for an executive about this {self._horizon}-day "
                f"forecast for {target_col}:\n"
                f"Model: {model_result.get('model')}\n"
                f"Trend: {model_result.get('trend_direction', 'unknown')}\n"
                f"First predictions: {sample}\n"
                "Be specific and business-focused. No jargon."
            )
            return await self._llm.complete(
                prompt=prompt, model_id=get_model_id("planner")
            )
        except Exception:
            return f"Forecast for {target_col} generated using {model_result.get('model', 'ML')}."
