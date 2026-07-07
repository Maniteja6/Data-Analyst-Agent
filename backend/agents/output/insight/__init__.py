"""Insight agent — LLM synthesis of all analysis outputs into a ranked report.

NarrativeGenerator streams the executive summary token-by-token via Socket.IO
using BedrockStreamAdapter so users see the AI response as it's generated.
Emits: insight:generation_start, insight:summary_token (N), insight:insight_ready (5),
       insight:kpi_ready (N), insight:complete.
"""

from backend.agents.output.insight.insight_agent import InsightAgent
from backend.agents.output.insight.narrative_generator import (
    NarrativeGenerator,
)

__all__ = ["InsightAgent", "NarrativeGenerator"]
