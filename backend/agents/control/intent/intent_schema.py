"""IntentClassification schema — typed output of the IntentAgent.

Used as the routing signal in the chat query LangGraph to decide whether
to invoke SQLAgent, ForecastAgent, RAGAgent, or return a direct answer.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Intent(str, Enum):
    """Enumeration of all supported user intents."""
    STATISTICAL_QUESTION   = "statistical_question"
    FORECASTING_REQUEST    = "forecasting_request"
    ANOMALY_INVESTIGATION  = "anomaly_investigation"
    DATA_EXPORT            = "data_export"
    GENERAL_QUESTION       = "general_question"
    SQL_QUERY              = "sql_query"
    VISUALIZATION_REQUEST  = "visualization_request"
    COMPARISON             = "comparison"
    TREND_ANALYSIS         = "trend_analysis"
    UNKNOWN                = "unknown"


class IntentEntities(BaseModel):
    """Named entities extracted from the user message."""
    column:      str | None = None   # "revenue", "region"
    metric:      str | None = None   # "average", "total", "count"
    time_range:  str | None = None   # "last quarter", "YTD", "2024"
    filter_val:  str | None = None   # "North", "Widget A"
    top_n:       int | None = None   # 5 (for "top 5 products")


class IntentClassification(BaseModel):
    """Structured output of the IntentAgent."""

    intent:      Intent         = Intent.UNKNOWN
    entities:    IntentEntities = Field(default_factory=IntentEntities)
    confidence:  float          = Field(default=0.5, ge=0.0, le=1.0)
    sub_intents: list[str]      = Field(default_factory=list)

    # Routing flags used by the chat query LangGraph
    requires_sql:       bool = False
    requires_rag:       bool = True
    requires_forecast:  bool = False
    requires_viz:       bool = False

    # Natural language rephrasing for improved RAG retrieval
    search_query: str = ""

    @classmethod
    def fallback(cls) -> IntentClassification:
        """Return a safe fallback classification when the LLM fails."""
        return cls(
            intent=Intent.GENERAL_QUESTION,
            confidence=0.3,
            requires_sql=False,
            requires_rag=True,
        )

    @property
    def is_high_confidence(self) -> bool:
        return self.confidence >= 0.75

    @property
    def routing_label(self) -> str:
        """Human-readable routing decision for logging."""
        routes = []
        if self.requires_sql:      routes.append("SQL")
        if self.requires_rag:      routes.append("RAG")
        if self.requires_forecast: routes.append("Forecast")
        if self.requires_viz:      routes.append("Viz")
        return " + ".join(routes) or "Direct"

    def to_dict(self) -> dict:
        return {
            "intent":            self.intent.value,
            "entities":          self.entities.model_dump(exclude_none=True),
            "confidence":        self.confidence,
            "sub_intents":       self.sub_intents,
            "requires_sql":      self.requires_sql,
            "requires_rag":      self.requires_rag,
            "requires_forecast": self.requires_forecast,
            "requires_viz":      self.requires_viz,
            "search_query":      self.search_query,
            "routing_label":     self.routing_label,
        }
