"""IntentClassification value object — output of the Intent Agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from backend.shared.value_object import ValueObject


class Intent(StrEnum):
    """Supported chat query intent types.

    The Intent Agent classifies each incoming user message into one of these
    categories. The ChatQueryGraph then routes to the appropriate analysis
    sub-graph based on the intent.
    """

    STATISTICAL_QUESTION = "statistical_question"
    """User wants a descriptive statistic: average, max, distribution, etc.
    → Routes to SQL Agent for aggregation queries.
    """

    FORECASTING_REQUEST = "forecasting_request"
    """User asks about future values or trends.
    → Routes to Forecast Agent.
    """

    ANOMALY_INVESTIGATION = "anomaly_investigation"
    """User wants to explore an anomaly flag or outlier.
    → Routes to SQL Agent + AnomalyAlert lookup.
    """

    SQL_QUERY = "sql_query"
    """User has written or wants a specific SQL query executed.
    → Routes directly to SQL Agent with the user's SQL.
    """

    VISUALIZATION_REQUEST = "visualization_request"
    """User wants a chart or plot.
    → Routes to SQL Agent + Visualization Agent.
    """

    DATA_EXPORT = "data_export"
    """User wants to download filtered data or a report.
    → Routes to Export use case.
    """

    GENERAL_QUESTION = "general_question"
    """Anything else — overview questions, explanations, comparisons.
    → Routes to RAG Agent + narrative response.
    """


@dataclass(frozen=True)
class IntentClassification(ValueObject):
    """Immutable output of the Intent Agent for a single user message.

    Stored on the ChatState during the chat query graph execution and
    used to route the query to the correct analysis sub-graph.

    Attributes:
        intent:         Primary intent category.
        confidence:     Model confidence for the primary intent (0.0–1.0).
        entities:       Extracted named entities from the user message.
                        Keys: ``'columns'``, ``'metrics'``, ``'time_period'``,
                        ``'comparison_groups'``, ``'filters'``.
        sub_intents:    Secondary intents when the message spans multiple goals.
        requires_sql:   True when the intent needs a DuckDB query.
        requires_rag:   True when the intent needs vector store retrieval.
        requires_chart: True when the response should include a Vega-Lite chart.
        raw_input:      The original user message (for audit logging).
    """

    intent: Intent
    confidence: float = 1.0
    entities: tuple = field(default_factory=tuple)  # frozen (key, val) pairs
    sub_intents: tuple[str, ...] = field(default_factory=tuple)
    requires_sql: bool = False
    requires_rag: bool = True
    requires_chart: bool = False
    raw_input: str = ""

    def _validate(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")

    # ── Accessors ─────────────────────────────────────────────────────────

    @property
    def entities_dict(self) -> dict:
        return dict(self.entities)

    @property
    def mentioned_columns(self) -> list[str]:
        """Dataset column names extracted from the user message."""
        return self.entities_dict.get("columns", [])

    @property
    def time_period(self) -> str | None:
        """Natural language time expression, e.g. ``'last 3 months'``."""
        return self.entities_dict.get("time_period")

    @property
    def is_high_confidence(self) -> bool:
        return self.confidence >= 0.8

    # ── Factory ───────────────────────────────────────────────────────────

    @classmethod
    def create(
        cls,
        intent: Intent | str,
        confidence: float = 1.0,
        entities: dict | None = None,
        sub_intents: list[str] | None = None,
        raw_input: str = "",
    ) -> IntentClassification:
        """Create an IntentClassification, inferring routing flags from the intent."""
        if isinstance(intent, str):
            intent = Intent(intent)

        sql_intents = {
            Intent.STATISTICAL_QUESTION,
            Intent.SQL_QUERY,
            Intent.ANOMALY_INVESTIGATION,
            Intent.VISUALIZATION_REQUEST,
        }
        chart_intents = {Intent.VISUALIZATION_REQUEST, Intent.FORECASTING_REQUEST}

        return cls(
            intent=intent,
            confidence=confidence,
            entities=tuple(sorted((entities or {}).items())),
            sub_intents=tuple(sub_intents or []),
            requires_sql=intent in sql_intents,
            requires_rag=intent not in {Intent.SQL_QUERY},
            requires_chart=intent in chart_intents,
            raw_input=raw_input,
        )

    def to_dict(self) -> dict:
        return {
            "intent": self.intent.value,
            "confidence": self.confidence,
            "entities": self.entities_dict,
            "sub_intents": list(self.sub_intents),
            "requires_sql": self.requires_sql,
            "requires_rag": self.requires_rag,
            "requires_chart": self.requires_chart,
        }
