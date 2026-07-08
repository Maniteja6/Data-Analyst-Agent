"""RecommendationAgent — converts insights into actionable recommendations.

Real-time pipeline:
    Each recommendation is enriched with an impact estimate and immediately
    emitted as a ``recommendation:ready`` Socket.IO event so the frontend
    can render the action cards one-by-one as they're generated.

    Progressive reveal: recommendations appear in priority order (high → low)
    so users always see the most important action first, even before all
    recommendations are ready.

Socket.IO events emitted:
    recommendation:start  — "Generating recommendations…"
    recommendation:ready  — per recommendation with estimated_impact dict
    recommendation:complete — full list of recommendations
"""

from __future__ import annotations

import contextlib
import json
import re
from typing import Any

import structlog
from backend.agents.base.agent_context import AgentContext
from backend.agents.base.base_agent import BaseAgent
from backend.agents.output.recommendation.impact_estimator import ImpactEstimator
from backend.infrastructure.llm.model_id_registry import get_model_id

logger = structlog.get_logger(__name__)

_SYSTEM = "You are a strategic business advisor. Return ONLY valid JSON. No markdown. No preamble."
_MAX_TOKENS = 1200


class RecommendationAgent(BaseAgent):
    """Converts InsightReport insights into 3 prioritised recommendations.

    Args:
        llm_client: Claude Sonnet client for recommendation generation.
    """

    def __init__(self, llm_client: Any = None) -> None:  # noqa: ANN401
        super().__init__("recommendation")
        self._llm = llm_client
        self._estimator = ImpactEstimator()

    async def _execute(self, context: AgentContext, **kwargs: Any) -> dict:  # noqa: ANN401
        """Generate recommendations from the current InsightReport.

        Returns:
            Dict with key ``recommendations``: list of 3 recommendation dicts,
            each with estimated_impact embedded.
        """
        sio = context._sio
        dataset_id = context.dataset_id
        insights = context.insight_results or []

        # Check for InsightReport passed directly (from report generator)
        insight_report = kwargs.get("insight_report", {})
        if insight_report:
            insights = insight_report.get("insights", insights)

        if not insights:
            return {"recommendations": []}

        if sio and dataset_id:
            with contextlib.suppress(Exception):
                await sio.emit(
                    "recommendation:start",
                    {"dataset_id": dataset_id},
                    room=f"dataset:{dataset_id}",
                )

        await context.push_progress(93, "Generating recommendations…", step="recommendation")

        # Generate recommendations via LLM
        recommendations = await self._generate(insights, context.schema or {})

        # Estimate impact for each recommendation
        anomaly_count = len(context.anomaly_results or [])
        forecast_trend = self._extract_trend(context.forecast_results or [])

        self._estimator.batch_estimate(
            recommendations=recommendations,
            insights=insights,
            schema=context.schema,
            anomaly_count=anomaly_count,
            forecast_trend=forecast_trend,
        )

        # Sort by priority: high → medium → low
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(key=lambda r: priority_order.get(r.get("priority", "low"), 2))

        # Emit each recommendation progressively
        if sio and dataset_id:
            for i, rec in enumerate(recommendations):
                with contextlib.suppress(Exception):
                    await sio.emit(
                        "recommendation:ready",
                        {
                            "dataset_id": dataset_id,
                            "rec_index": i,
                            "recommendation": rec,
                        },
                        room=f"dataset:{dataset_id}",
                    )

        if sio and dataset_id:
            with contextlib.suppress(Exception):
                await sio.emit(
                    "recommendation:complete",
                    {
                        "dataset_id": dataset_id,
                        "recommendation_count": len(recommendations),
                    },
                    room=f"dataset:{dataset_id}",
                )

        context.recommendations = recommendations
        logger.info(
            "recommendation_agent_complete",
            count=len(recommendations),
            dataset_id=dataset_id,
        )
        return {"recommendations": recommendations}

    # ── LLM generation ────────────────────────────────────────────────────

    async def _generate(self, insights: list[dict], schema: dict) -> list[dict]:
        if not self._llm:
            return self._fallback_recommendations(insights)

        col_count = schema.get("column_count", len(schema.get("columns", [])))
        row_count = schema.get("row_count_sample", 0)
        col_names = [c["name"] for c in schema.get("columns", [])[:10]]

        insights_json = json.dumps(
            [
                {
                    "headline": ins.get("headline", ""),
                    "business_impact": ins.get("business_impact", "medium"),
                    "confidence": ins.get("confidence", 0.8),
                }
                for ins in insights[:5]
            ],
            indent=2,
        )

        prompt = (
            f"Convert these data insights into 3 actionable business recommendations.\n\n"
            f"DATASET CONTEXT:\n"
            f"  Rows: {row_count:,} | Columns: {col_count}\n"
            f"  Key columns: {col_names}\n\n"
            f"INSIGHTS:\n{insights_json}\n\n"
            "Return ONLY a JSON array of exactly 3 recommendations:\n"
            "[\n"
            "  {\n"
            '    "title": "Short action title (5-7 words)",\n'
            '    "priority": "high|medium|low",\n'
            '    "situation": "One sentence: what the data reveals that drives this action.",\n'
            '    "action": "One to two sentences: specific, implementable action to take.",\n'
            '    "estimated_impact": "Quantified benefit range (e.g. \'15-20% reduction in X\')"\n'
            "  }\n"
            "]"
        )
        try:
            raw = await self._llm.complete(
                prompt=prompt,
                system=_SYSTEM,
                model_id=get_model_id("planner"),
                max_tokens=_MAX_TOKENS,
            )
            recs = self._parse_response(raw)
            if recs:
                return recs
        except Exception as exc:
            logger.warning("recommendation_generation_failed", error=str(exc))

        return self._fallback_recommendations(insights)

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _parse_response(raw: str) -> list[dict]:
        text = raw.strip()
        if text.startswith("```"):
            text = "\n".join(
                line for line in text.splitlines() if not line.startswith("``")
            ).strip()
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data[:3]
        except json.JSONDecodeError:
            match = re.search(r"\[.*?\]", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())[:3]
                except json.JSONDecodeError:
                    pass
        return []

    @staticmethod
    def _extract_trend(forecasts: list[dict]) -> str:
        if not forecasts:
            return "unknown"
        return forecasts[0].get("trend_direction", "unknown")

    @staticmethod
    def _fallback_recommendations(insights: list[dict]) -> list[dict]:
        if not insights:
            return []
        top = insights[0]
        return [
            {
                "title": f"Address: {top.get('headline', 'key finding')[:40]}",
                "priority": top.get("business_impact", "medium"),
                "situation": top.get("explanation", "")[:150],
                "action": "Review this finding with your data team and define next steps.",
                "estimated_impact": "Impact estimation requires LLM integration.",
            }
        ]
