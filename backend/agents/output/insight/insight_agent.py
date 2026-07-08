"""InsightAgent — synthesises all analysis outputs into a ranked InsightReport.

Real-time pipeline:
    1. Build context from all parallel agent results (SQL, Forecast, ML, Anomaly)
    2. Generate 5 ranked insights via Claude Sonnet
    3. Stream the executive summary token-by-token via Socket.IO
    4. Emit ``insight:insight_ready`` for each insight progressively
    5. Calculate KPIs from the DataProfile
    6. Emit ``insight:complete`` with the full report

Socket.IO events emitted:
    insight:generation_start — "Generating insights…"
    insight:summary_token    — one per token during executive summary streaming
    insight:summary_complete — full executive summary string
    insight:insight_ready    — per insight as it's revealed progressively
    insight:kpi_ready        — per KPI computed
    insight:complete         — full InsightReport payload

Progressive reveal strategy:
    Insights are revealed one-by-one (not all at once) because it creates a
    more engaging UX — users start reading insight #1 while #2–#5 are still
    being polished by NarrativeGenerator. Target: first insight visible within
    2 seconds of analysis completing.
"""

from __future__ import annotations

import contextlib
import json
import re
from typing import Any

import structlog
from backend.agents.base.agent_context import AgentContext
from backend.agents.base.base_agent import BaseAgent
from backend.agents.output.insight.narrative_generator import NarrativeGenerator
from backend.infrastructure.llm.model_id_registry import get_model_id

logger = structlog.get_logger(__name__)

_MAX_INSIGHT_TOKENS = 2000

_SYSTEM = (
    "You are a senior data analyst generating business insights. "
    "Return ONLY valid JSON. No markdown. No explanation."
)


class InsightAgent(BaseAgent):
    """Synthesises analysis outputs into a ranked InsightReport with streaming summary.

    Args:
        llm_client:    Claude Sonnet for insight generation (batch).
        stream_client: BedrockStreamAdapter for executive summary streaming.
    """

    def __init__(self, llm_client: Any = None, stream_client: Any = None) -> None:  # noqa: ANN401
        super().__init__("insight")
        self._llm = llm_client
        self._stream = stream_client

    async def _execute(self, context: AgentContext, **kwargs: Any) -> dict:  # noqa: ANN401
        """Generate the InsightReport for a completed analysis session.

        Args:
            context: Shared pipeline state with all parallel agent results.

        Returns:
            InsightReport dict with: executive_summary, insights, kpis,
            anomaly_alerts, forecasts, recommendations (empty list — filled
            by RecommendationAgent), is_critic_validated (False initially).
        """
        sio = context._sio
        dataset_id = context.dataset_id
        previous_critique = kwargs.get("previous_critique")

        # ── Notify frontend insight generation is starting ─────────────────
        if sio and dataset_id:
            with contextlib.suppress(Exception):
                await sio.emit(
                    "insight:generation_start",
                    {"dataset_id": dataset_id, "session_id": context.session_id},
                    room=f"dataset:{dataset_id}",
                )

        await context.push_progress(78, "Generating business insights…", step="insight")

        # ── Build context from all agent outputs ──────────────────────────
        profile = context.profile or {}
        sql_rows = context.sql_results or []
        anomalies = context.anomaly_results or []
        forecasts = context.forecast_results or []
        ml_result = context.ml_results or {}

        sql_summary = self._summarise_sql(sql_rows)
        anomaly_summary = self._summarise_anomalies(anomalies)
        forecast_summary = self._summarise_forecasts(forecasts)
        ml_summary = self._summarise_ml(ml_result)

        # ── Generate 5 ranked insights ────────────────────────────────────
        insights = await self._generate_insights(
            profile=profile,
            sql_summary=sql_summary,
            anomaly_summary=anomaly_summary,
            forecast_summary=forecast_summary,
            ml_summary=ml_summary,
            schema=context.schema or {},
            previous_critique=previous_critique,
        )

        # ── Compute KPIs from DataProfile ─────────────────────────────────
        kpis = self._compute_kpis(profile, sio, dataset_id)

        # ── Progressive insight reveal via Socket.IO ──────────────────────
        if sio and dataset_id:
            for i, insight in enumerate(insights):
                with contextlib.suppress(Exception):
                    await sio.emit(
                        "insight:insight_ready",
                        {
                            "dataset_id": dataset_id,
                            "insight_index": i,
                            "insight": insight,
                        },
                        room=f"dataset:{dataset_id}",
                    )

        # ── Stream executive summary token-by-token ───────────────────────
        narrator = NarrativeGenerator(
            llm_client=self._llm,
            stream_client=self._stream,
            sio=sio,
            dataset_id=dataset_id,
        )
        executive_summary = await narrator.generate_executive_summary_streaming(
            profile=profile,
            insights=insights,
            sql_summary=sql_summary,
            anomaly_count=len(anomalies),
            forecast_summary=forecast_summary,
        )

        # ── Build final report dict ───────────────────────────────────────
        report = {
            "session_id": context.session_id,
            "dataset_id": dataset_id,
            "executive_summary": executive_summary,
            "insights": insights,
            "kpis": kpis,
            "anomaly_alerts": anomalies[:20],  # cap at 20 for UI
            "forecasts": forecasts,
            "recommendations": [],  # filled by RecommendationAgent
            "is_critic_validated": False,
            "has_forecasts": bool(forecasts),
            "has_anomalies": bool(anomalies),
            "insight_count": len(insights),
        }

        # ── Emit insight:complete ─────────────────────────────────────────
        if sio and dataset_id:
            with contextlib.suppress(Exception):
                await sio.emit(
                    "insight:complete",
                    {
                        "dataset_id": dataset_id,
                        "insight_count": len(insights),
                        "kpi_count": len(kpis),
                        "has_forecasts": bool(forecasts),
                        "has_anomalies": bool(anomalies),
                    },
                    room=f"dataset:{dataset_id}",
                )

        context.insight_results = insights
        logger.info(
            "insight_agent_complete",
            dataset_id=dataset_id,
            insight_count=len(insights),
            kpi_count=len(kpis),
        )
        return report

    # ── Insight generation ────────────────────────────────────────────────

    async def _generate_insights(
        self,
        profile: dict,
        sql_summary: str,
        anomaly_summary: str,
        forecast_summary: str,
        ml_summary: str,
        schema: dict,
        previous_critique: dict | None = None,
    ) -> list[dict]:
        """Call Claude Sonnet to generate 5 ranked insights."""
        if not self._llm:
            return self._fallback_insights(profile)

        critique_block = ""
        if previous_critique and previous_critique.get("issues"):
            issues_text = "\n".join(
                f"- {issue.get('description', '')}" for issue in previous_critique.get("issues", [])
            )
            critique_block = (
                f"\n\nPREVIOUS CRITIQUE — fix these issues in this revision:\n{issues_text}"
            )

        col_names = [c["name"] for c in schema.get("columns", [])[:20]]

        prompt = (
            f"Generate exactly 5 ranked business insights from this data analysis.\n\n"
            f"DATASET OVERVIEW:\n"
            f"  Rows: {profile.get('row_count', 0):,} | "
            f"Cols: {profile.get('column_count', 0)} | "
            f"Completeness: {profile.get('completeness_score', 1.0):.1%}\n"
            f"  Columns: {col_names[:10]}\n\n"
            f"SQL QUERY FINDINGS:\n{sql_summary or 'No SQL results available.'}\n\n"
            f"ANOMALY ALERTS:\n{anomaly_summary or 'No anomalies detected.'}\n\n"
            f"FORECAST:\n{forecast_summary or 'No forecast available.'}\n\n"
            f"ML FINDINGS:\n{ml_summary or 'No ML analysis available.'}"
            f"{critique_block}\n\n"
            "Return ONLY a JSON array of exactly 5 insights:\n"
            "[\n"
            "  {\n"
            '    "headline": "Specific, factual headline with a number (10-15 words)",\n'
            '    "explanation": "2-3 sentences citing specific columns and values",\n'
            '    "business_impact": "high|medium|low",\n'
            '    "confidence": 0.90,\n'
            '    "source_columns": ["col_a", "col_b"],\n'
            '    "has_anomaly_reference": false\n'
            "  }\n"
            "]"
        )

        try:
            raw = await self._llm.complete(
                prompt=prompt,
                system=_SYSTEM,
                model_id=get_model_id("insight"),
                max_tokens=_MAX_INSIGHT_TOKENS,
            )
            insights = self._parse_insights(raw)
            if insights:
                return insights
        except Exception as exc:
            logger.warning("insight_generation_failed", error=str(exc))

        return self._fallback_insights(profile)

    # ── KPI calculation ───────────────────────────────────────────────────

    def _compute_kpis(self, profile: dict, sio: Any, dataset_id: str) -> list[dict]:  # noqa: ANN401
        """Build KPI cards from the DataProfile statistics."""
        import asyncio

        kpis = [
            {
                "name": "Total Rows",
                "value": profile.get("row_count", 0),
                "unit": "rows",
                "format": "integer",
                "trend": None,
            },
            {
                "name": "Columns",
                "value": profile.get("column_count", 0),
                "unit": "cols",
                "format": "integer",
                "trend": None,
            },
            {
                "name": "Completeness",
                "value": round(profile.get("completeness_score", 1.0) * 100, 1),
                "unit": "%",
                "format": "percent",
                "trend": None,
                "benchmark": 95.0,
            },
            {
                "name": "Duplicate Rows",
                "value": profile.get("duplicate_count", 0),
                "unit": "rows",
                "format": "integer",
                "trend": None,
            },
        ]

        # Add per-column KPIs for numeric/currency columns
        for col in profile.get("column_profiles", []):
            stats = col.get("stats") or {}
            if not stats or col.get("kind") not in ("numeric",):
                continue
            stype = col.get("semantic_type", "")
            if stype == "currency":
                kpis.append(
                    {
                        "name": f"Avg {col['column_name']}",
                        "value": round(stats.get("mean", 0), 2),
                        "unit": "",
                        "format": "currency",
                        "trend": None,
                    }
                )
            if len(kpis) >= 10:
                break

        # Emit each KPI as it's computed
        if sio and dataset_id:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(self._emit_kpis(sio, dataset_id, kpis))
            except Exception as exc:
                logger.debug("kpi_emit_scheduling_failed", error=str(exc))

        return kpis

    @staticmethod
    async def _emit_kpis(sio: Any, dataset_id: str, kpis: list[dict]) -> None:  # noqa: ANN401
        for i, kpi in enumerate(kpis):
            with contextlib.suppress(Exception):
                await sio.emit(
                    "insight:kpi_ready",
                    {"dataset_id": dataset_id, "kpi_index": i, "kpi": kpi},
                    room=f"dataset:{dataset_id}",
                )

    # ── Summarisers ───────────────────────────────────────────────────────

    @staticmethod
    def _summarise_sql(sql_results: list[dict]) -> str:
        if not sql_results:
            return ""
        parts = []
        for r in sql_results[:3]:
            if isinstance(r, dict):
                summary = r.get("summary", "") or r.get("markdown_table", "")[:300]
                if summary:
                    parts.append(summary)
        return "\n".join(parts)

    @staticmethod
    def _summarise_anomalies(anomalies: list[dict]) -> str:
        if not anomalies:
            return ""
        high = [a for a in anomalies if a.get("severity") == "high"]
        sample = high[:3] if high else anomalies[:3]
        return "\n".join(
            f"- [{a.get('severity', '?').upper()}] {a.get('description', '')}" for a in sample
        )

    @staticmethod
    def _summarise_forecasts(forecasts: list[dict]) -> str:
        if not forecasts:
            return ""
        f = forecasts[0]
        return (
            f"{f.get('target_column', '?')} forecast over {f.get('horizon_label', '?')}: "
            f"trend is {f.get('trend_direction', 'unknown')}. "
            f"Model: {f.get('model_name', '?')}."
        )

    @staticmethod
    def _summarise_ml(ml_result: dict) -> str:
        if not ml_result or ml_result.get("error"):
            return ""
        return (
            f"{ml_result.get('task', '?')} model predicting {ml_result.get('target', '?')}. "
            f"CV score: {ml_result.get('cv_score_mean', 0):.3f}. "
            f"Top features: {list((ml_result.get('feature_importances') or {}).keys())[:3]}."
        )

    # ── Parsers and fallbacks ─────────────────────────────────────────────

    @staticmethod
    def _parse_insights(raw: str) -> list[dict]:
        text = raw.strip()
        if text.startswith("```"):
            text = "\n".join(
                line for line in text.splitlines() if not line.startswith("``")
            ).strip()
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data[:5]
            if isinstance(data, dict) and "insights" in data:
                return data["insights"][:5]
        except json.JSONDecodeError:
            match = re.search(r"\[.*?\]", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())[:5]
                except json.JSONDecodeError:
                    pass
        return []

    @staticmethod
    def _fallback_insights(profile: dict) -> list[dict]:
        """Return basic data quality insights when the LLM is unavailable."""
        row_count = profile.get("row_count", 0)
        col_count = profile.get("column_count", 0)
        completeness = profile.get("completeness_score", 1.0)
        dup_count = profile.get("duplicate_count", 0)

        insights: list[dict] = [
            {
                "headline": f"Dataset contains {row_count:,} rows across {col_count} columns",
                "explanation": "Basic dataset dimensions are confirmed and ready for analysis.",
                "business_impact": "medium",
                "confidence": 1.0,
                "source_columns": [],
                "has_anomaly_reference": False,
            },
            {
                "headline": f"Data completeness is {completeness:.1%}",
                "explanation": "This measures the proportion of non-null values across all fields.",
                "business_impact": "high" if completeness < 0.90 else "low",
                "confidence": 1.0,
                "source_columns": [],
                "has_anomaly_reference": False,
            },
        ]
        if dup_count > 0:
            insights.append(
                {
                    "headline": f"{dup_count:,} duplicate rows detected",
                    "explanation": "Duplicate records were found and removed during data cleaning.",
                    "business_impact": "medium",
                    "confidence": 1.0,
                    "source_columns": [],
                    "has_anomaly_reference": False,
                }
            )
        return insights
