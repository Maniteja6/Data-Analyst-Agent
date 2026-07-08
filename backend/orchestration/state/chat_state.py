"""ChatState — shared state for the chat query LangGraph graph.

A separate state class from PipelineState to keep chat-specific fields
(conversation history, intent classification, RAG chunks) isolated from
the batch analysis pipeline state.

Chat query graph flow:
  input → IntentNode → [SQLNode | RAGNode | ForecastNode] → InsightNode →
  ValidatorNode → SecurityNode → ResponseFormatterNode → output

Each node reads from and writes to this shared state dict.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict


class ChatState(TypedDict, total=False):
    """Mutable state flowing through the chat query graph.

    ``total=False`` means all fields are optional.
    """

    # ── Request context ───────────────────────────────────────────────────
    user_message: str
    """The raw user message as received from the WebSocket."""

    conversation_id: str
    """UUID of the Conversation aggregate."""

    dataset_id: str
    """Dataset the user is querying."""

    session_id: str
    """Most recent AnalysisSession for this dataset (provides insight context)."""

    correlation_id: str
    """Request-scoped tracing ID."""

    # ── Conversation history ──────────────────────────────────────────────
    messages: list[dict]
    """Full Bedrock Converse API message history for multi-turn context."""

    system_prompt: str
    """Constructed system prompt including schema summary and RAG context."""

    # ── Intent classification (IntentNode output) ─────────────────────────
    intent: dict[str, Any]
    """IntentClassification.to_dict() — intent, entities, routing flags."""

    # ── Analysis sub-agent outputs ────────────────────────────────────────
    sql_result: dict[str, Any]
    """{'sql': str, 'rows': list[dict], 'markdown_table': str}."""

    rag_context: str
    """Concatenated top-K RAG chunk texts retrieved for the query."""

    forecast_result: dict[str, Any]
    """ForecastResult.to_dict() when the query triggers the Forecast Agent."""

    # ── Response construction ─────────────────────────────────────────────
    assistant_response: str
    """The final natural-language response text for the user."""

    citations: list[dict]
    """Source references extracted from the response."""

    visualizations: list[dict]
    """Vega-Lite chart specs to embed in the response."""

    # ── Safety checks ─────────────────────────────────────────────────────
    pii_detected: bool
    """True when the SecurityNode detected PII in the user message."""

    injection_detected: bool
    """True when the SecurityNode detected a prompt injection attempt."""

    is_valid: bool
    """True when the ValidatorNode approves the draft response."""

    # ── Accumulating ─────────────────────────────────────────────────────
    errors: Annotated[list[str], operator.add]
    """Error messages accumulated across nodes."""

    metadata: dict[str, Any]
    """Token counts, latency, model IDs."""
