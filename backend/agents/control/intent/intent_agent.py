"""IntentAgent — classifies chat messages and extracts routing signals.

Uses Claude Haiku (the fast model) to minimise latency on every chat message.
Target: < 500ms end-to-end for classification + routing signal extraction.

Real-time design:
    The IntentAgent is the first node in the chat query LangGraph. Its output
    determines which agents run next (SQL, RAG, Forecast, Viz) so it must
    complete quickly. Haiku at ~200ms vs Sonnet at ~1.5s makes a significant
    UX difference in real-time chat.

Output routing:
    requires_sql       → SQLAgent
    requires_forecast  → ForecastAgent
    requires_viz       → VisualizationAgent
    requires_rag       → RAGAgent (always True as fallback)
"""
from __future__ import annotations

import json
from typing import Any

import structlog
from backend.agents.base.agent_context import AgentContext
from backend.agents.base.base_agent import BaseAgent
from backend.agents.control.intent.intent_schema import (
    Intent,
    IntentClassification,
    IntentEntities,
)
from backend.infrastructure.llm.model_id_registry import get_model_id

logger = structlog.get_logger(__name__)

_SYSTEM = (
    "You are an intent classifier for a data analytics assistant. "
    "Return ONLY valid JSON. No explanation. No markdown."
)

# Keyword-based pre-classifier to save LLM calls for obvious intents
_SQL_KEYWORDS = frozenset({
    "total", "sum", "average", "avg", "count", "group", "top", "filter", "where",
    "how many",
})
_FORECAST_WORDS = frozenset({
    "forecast", "predict", "future", "trend", "next month", "next quarter",
    "projection",
})
_VIZ_WORDS = frozenset({
    "chart", "graph", "plot", "visualise", "visualize", "show me a", "pie",
    "bar chart",
})
_ANOMALY_WORDS = frozenset({
    "anomaly", "outlier", "unusual", "spike", "drop", "strange", "weird",
    "wrong",
})


class IntentAgent(BaseAgent):
    """Classifies user intent and extracts routing entities.

    Args:
        llm_client: Async LLM client (Claude Haiku for low latency).
        use_fast_path: When True, use keyword pre-classification to skip
                       the LLM call for unambiguous intents.
    """

    def __init__(self, llm_client: Any, use_fast_path: bool = True) -> None:
        super().__init__("intent")
        self._llm       = llm_client
        self._fast_path = use_fast_path

    async def _execute(
        self,
        context: AgentContext,
        user_message: str = "",
        **kwargs: Any,
    ) -> dict:
        """Classify the user message and return an IntentClassification dict.

        Args:
            context:      Shared context (schema used for column hints).
            user_message: The raw user message from the WebSocket.

        Returns:
            IntentClassification.to_dict()
        """
        if not user_message.strip():
            return IntentClassification.fallback().to_dict()

        # ── Fast-path: keyword classification ────────────────────────────
        if self._fast_path:
            fast = self._keyword_classify(user_message)
            if fast and fast.is_high_confidence:
                logger.debug(
                    "intent_fast_path",
                    intent=fast.intent.value,
                    confidence=fast.confidence,
                )
                return fast.to_dict()

        # ── LLM classification ────────────────────────────────────────────
        schema_cols = []
        if context.schema:
            schema_cols = [c["name"] for c in context.schema.get("columns", [])]

        prompt = self._build_prompt(user_message, schema_cols)

        try:
            raw = await self._llm.complete(
                prompt=prompt,
                system=_SYSTEM,
                model_id=get_model_id("intent"),
                max_tokens=400,
            )
            data         = self._parse_response(raw)
            intent       = data.get("intent", "general_question")
            entities_raw = data.get("entities", {})
            entities     = IntentEntities(
                column=entities_raw.get("column"),
                metric=entities_raw.get("metric"),
                time_range=entities_raw.get("time_range"),
                filter_val=entities_raw.get("filter_value"),
                top_n=entities_raw.get("top_n"),
            )
            classification = IntentClassification(
                intent=Intent(intent) if intent in Intent._value2member_map_ else Intent.GENERAL_QUESTION,
                entities=entities,
                confidence=float(data.get("confidence", 0.85)),
                sub_intents=data.get("sub_intents", []),
                requires_sql=bool(data.get("requires_sql", False)),
                requires_rag=bool(data.get("requires_rag", True)),
                requires_forecast=bool(data.get("requires_forecast", False)),
                requires_viz=bool(data.get("requires_viz", False)),
                search_query=data.get("search_query", user_message),
            )
        except Exception as exc:
            logger.warning("intent_llm_parse_failed", error=str(exc))
            classification = IntentClassification.fallback()

        logger.info(
            "intent_classified",
            intent=classification.intent.value,
            routing=classification.routing_label,
            confidence=classification.confidence,
        )
        return classification.to_dict()

    def _build_prompt(self, message: str, column_names: list[str]) -> str:
        col_hint = f"\nDataset columns (use to detect column references): {column_names[:20]}" if column_names else ""
        return f"""Classify this data analytics chat message.{col_hint}

USER MESSAGE: {message}

Return ONLY valid JSON:
{{
  "intent": "<one of: statistical_question|forecasting_request|anomaly_investigation|data_export|general_question|sql_query|visualization_request|comparison|trend_analysis>",
  "entities": {{
    "column": "<column name if mentioned, else null>",
    "metric": "<sum|avg|count|max|min if mentioned, else null>",
    "time_range": "<time period if mentioned, else null>",
    "filter_value": "<filter value if mentioned, else null>",
    "top_n": <integer if mentioned, else null>
  }},
  "confidence": 0.90,
  "sub_intents": [],
  "requires_sql": true,
  "requires_rag": false,
  "requires_forecast": false,
  "requires_viz": false,
  "search_query": "<rephrased as a factual search query>"
}}"""

    @staticmethod
    def _parse_response(raw: str) -> dict:
        """Parse LLM response, stripping any accidental markdown fences."""
        text = raw.strip()
        if text.startswith("```"):
            lines = [line for line in text.splitlines() if not line.startswith("```")]
            text = "\n".join(lines).strip()
        return json.loads(text)

    @staticmethod
    def _keyword_classify(message: str) -> IntentClassification | None:
        """Fast keyword-based pre-classification (no LLM call)."""
        msg = message.lower()

        if any(kw in msg for kw in _FORECAST_WORDS):
            return IntentClassification(
                intent=Intent.FORECASTING_REQUEST,
                confidence=0.80,
                requires_sql=False,
                requires_rag=True,
                requires_forecast=True,
                search_query=message,
            )

        if any(kw in msg for kw in _VIZ_WORDS):
            return IntentClassification(
                intent=Intent.VISUALIZATION_REQUEST,
                confidence=0.80,
                requires_sql=True,
                requires_rag=False,
                requires_viz=True,
                search_query=message,
            )

        if any(kw in msg for kw in _ANOMALY_WORDS):
            return IntentClassification(
                intent=Intent.ANOMALY_INVESTIGATION,
                confidence=0.78,
                requires_sql=False,
                requires_rag=True,
                search_query=message,
            )

        if any(kw in msg for kw in _SQL_KEYWORDS):
            return IntentClassification(
                intent=Intent.STATISTICAL_QUESTION,
                confidence=0.75,
                requires_sql=True,
                requires_rag=False,
                search_query=message,
            )

        return None   # fall through to LLM
