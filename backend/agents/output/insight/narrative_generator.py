"""NarrativeGenerator — streams the executive summary token-by-token via Socket.IO.

Real-time design:
    The executive summary is the first thing users see on the insight panel.
    Rather than waiting 3-5 seconds for the full response, NarrativeGenerator
    uses BedrockStreamAdapter to push each token the moment it arrives.

    The frontend renders the summary word-by-word in a typewriter effect,
    making the AI analysis feel instant even before all insights are computed.

Socket.IO events emitted:
    insight:summary_token    — one per LLM token during streaming
    insight:summary_complete — final summary string when streaming ends
    insight:kpi_ready        — fired after each KPI is computed

Two generation modes:
    STREAMING: for live WebSocket chat (default)
    BATCH:     for Celery report generation (no Socket.IO server)
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import structlog
from backend.infrastructure.llm.model_id_registry import get_model_id

logger = structlog.get_logger(__name__)

_MAX_SUMMARY_TOKENS = 600
_MAX_INSIGHT_TOKENS = 200


class NarrativeGenerator:
    """Generates streaming and batch LLM narratives for insights.

    Args:
        llm_client:    Async LLM client for batch completion (Sonnet).
        stream_client: BedrockStreamAdapter for token-by-token streaming.
                       Falls back to llm_client when None.
        sio:           Socket.IO server for real-time token events.
        dataset_id:    Dataset UUID for room targeting.
    """

    def __init__(
        self,
        llm_client: Any = None,  # noqa: ANN401
        stream_client: Any = None,  # noqa: ANN401
        sio: Any = None,  # noqa: ANN401
        dataset_id: str = "",
    ) -> None:
        self._llm = llm_client
        self._stream = stream_client
        self._sio = sio
        self._dataset_id = dataset_id

    # ── Executive summary (streaming) ─────────────────────────────────────

    async def generate_executive_summary_streaming(
        self,
        profile: dict,
        insights: list[dict],
        sql_summary: str = "",
        anomaly_count: int = 0,
        forecast_summary: str = "",
    ) -> str:
        """Generate the executive summary and stream tokens to Socket.IO.

        Args:
            profile:          DataProfile dict for dataset statistics.
            insights:         List of insight dicts from the LLM.
            sql_summary:      Summary of SQL query results.
            anomaly_count:    Number of anomalies detected.
            forecast_summary: One-line forecast direction string.

        Returns:
            Complete executive summary string (accumulated from stream).
        """
        prompt = self._build_executive_summary_prompt(
            profile, insights, sql_summary, anomaly_count, forecast_summary
        )

        streamer = self._stream or self._llm
        if streamer is None:
            return self._fallback_summary(profile, insights)

        tokens: list[str] = []
        message_id = f"summary_{self._dataset_id}"

        try:
            if hasattr(streamer, "stream"):
                # BedrockStreamAdapter — true token streaming
                async for token in streamer.stream(
                    prompt=prompt,
                    model_id=get_model_id("insight"),
                    max_tokens=_MAX_SUMMARY_TOKENS,
                ):
                    tokens.append(token)
                    await self._emit_token(token, message_id)
            else:
                # Batch client — emit whole response as one "token"
                full = await streamer.complete(
                    prompt=prompt,
                    model_id=get_model_id("insight"),
                    max_tokens=_MAX_SUMMARY_TOKENS,
                )
                tokens.append(full)
                await self._emit_token(full, message_id)

            summary = "".join(tokens).strip()

        except Exception as exc:
            logger.warning("executive_summary_stream_failed", error=str(exc))
            summary = self._fallback_summary(profile, insights)

        # Emit the complete event with the full text
        if self._sio and self._dataset_id:
            with contextlib.suppress(Exception):
                await self._sio.emit(
                    "insight:summary_complete",
                    {
                        "dataset_id": self._dataset_id,
                        "summary": summary,
                        "message_id": message_id,
                    },
                    room=f"dataset:{self._dataset_id}",
                )

        logger.info(
            "executive_summary_generated",
            chars=len(summary),
            streaming=self._stream is not None,
        )
        return summary

    # ── Per-insight headline rewriting ────────────────────────────────────

    async def rewrite_insight_headlines(
        self,
        insights: list[dict],
        emit_individually: bool = True,
    ) -> list[dict]:
        """Polish each insight headline to be more specific and punchy.

        Args:
            insights:           List of insight dicts with 'headline' keys.
            emit_individually:  When True, emit ``insight:insight_ready``
                                for each improved insight as it's generated
                                (real-time progressive reveal).

        Returns:
            Updated insights list with improved headlines.
        """
        if not insights or not self._llm:
            return insights

        async def _rewrite_one(i: int, insight: dict) -> tuple[int, dict]:
            try:
                prompt = (
                    f"Rewrite this data insight headline to be more specific, "
                    f"punchy, and business-focused. Include at least one number or "
                    f"percentage where possible. Maximum 15 words.\n\n"
                    f"Original: {insight.get('headline', '')}\n"
                    f"Context: {insight.get('explanation', '')[:200]}\n\n"
                    "New headline (ONLY the headline, no quotes):"
                )
                new_headline = await self._llm.complete(
                    prompt=prompt,
                    model_id=get_model_id("insight"),
                    max_tokens=50,
                )
                updated = {**insight, "headline": new_headline.strip()}

                if emit_individually and self._sio and self._dataset_id:
                    with contextlib.suppress(Exception):
                        await self._sio.emit(
                            "insight:insight_ready",
                            {
                                "dataset_id": self._dataset_id,
                                "insight_index": i,
                                "insight": updated,
                            },
                            room=f"dataset:{self._dataset_id}",
                        )

                return i, updated
            except Exception:
                return i, insight

        # Rewrite all headlines concurrently
        tasks = [_rewrite_one(i, ins) for i, ins in enumerate(insights)]
        results = await asyncio.gather(*tasks)

        # Re-sort to original order
        ordered = sorted(results, key=lambda x: x[0])
        return [r[1] for r in ordered]

    # ── Batch mode (for Celery report generation) ─────────────────────────

    async def generate_executive_summary_batch(
        self,
        profile: dict,
        insights: list[dict],
        **kwargs: Any,  # noqa: ANN401
    ) -> str:
        """Generate the executive summary without streaming (for Celery tasks)."""
        if not self._llm:
            return self._fallback_summary(profile, insights)
        prompt = self._build_executive_summary_prompt(
            profile,
            insights,
            kwargs.get("sql_summary", ""),
            kwargs.get("anomaly_count", 0),
            kwargs.get("forecast_summary", ""),
        )
        try:
            return await self._llm.complete(
                prompt=prompt,
                model_id=get_model_id("insight"),
                max_tokens=_MAX_SUMMARY_TOKENS,
            )
        except Exception as exc:
            logger.warning("executive_summary_batch_failed", error=str(exc))
            return self._fallback_summary(profile, insights)

    # ── Private helpers ───────────────────────────────────────────────────

    async def _emit_token(self, token: str, message_id: str) -> None:
        if self._sio and self._dataset_id:
            with contextlib.suppress(Exception):
                await self._sio.emit(
                    "insight:summary_token",
                    {"dataset_id": self._dataset_id, "token": token, "message_id": message_id},
                    room=f"dataset:{self._dataset_id}",
                )

    @staticmethod
    def _build_executive_summary_prompt(
        profile: dict,
        insights: list[dict],
        sql_summary: str,
        anomaly_count: int,
        forecast_summary: str,
    ) -> str:
        headlines = "\n".join(f"- {ins.get('headline', '')}" for ins in insights[:5])
        return (
            f"Write a 3-sentence executive summary for a business data analysis.\n\n"
            f"DATASET STATS:\n"
            f"  Rows: {profile.get('row_count', 'unknown'):,}\n"
            f"  Columns: {profile.get('column_count', 'unknown')}\n"
            f"  Completeness: {profile.get('completeness_score', 1.0):.1%}\n"
            f"  Anomalies detected: {anomaly_count}\n"
            f"  Forecast: {forecast_summary or 'not available'}\n\n"
            f"TOP FINDINGS:\n{headlines}\n\n"
            f"SQL INSIGHTS:\n{sql_summary[:300] or 'not available'}\n\n"
            "Write a concise executive summary for a non-technical business leader. "
            "Sentence 1: what the data shows. Sentence 2: most important finding with a number. "
            "Sentence 3: recommended action. No bullet points. Active voice."
        )

    @staticmethod
    def _fallback_summary(profile: dict, insights: list[dict]) -> str:
        rows = profile.get("row_count", 0)
        cols = profile.get("column_count", 0)
        top = insights[0].get("headline", "") if insights else "No significant findings"
        return (
            f"The dataset contains {rows:,} rows and {cols} columns "
            f"with a completeness score of "
            f"{profile.get('completeness_score', 1.0):.1%}. "
            f"Key finding: {top}."
        )
