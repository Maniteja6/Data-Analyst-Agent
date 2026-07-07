"""Intent classification — routes chat messages to the correct agent chain.

IntentAgent uses keyword pre-classification (< 1ms, no LLM) for unambiguous
queries (SQL aggregations, forecast requests, chart requests) and falls back
to Claude Haiku (~200ms) for ambiguous intents.
"""

from backend.agents.control.intent.intent_agent import IntentAgent
from backend.agents.control.intent.intent_schema import (
    Intent,
    IntentClassification,
    IntentEntities,
)

__all__ = ["IntentAgent", "Intent", "IntentClassification", "IntentEntities"]
