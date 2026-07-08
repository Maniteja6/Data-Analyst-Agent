"""CriticNode — validates and optionally revises the InsightReport."""

from __future__ import annotations

import structlog
from backend.config.feature_flags import flags
from backend.orchestration.state.pipeline_state import PipelineState

logger = structlog.get_logger(__name__)


async def critic_node(state: PipelineState) -> dict:
    """LangGraph node: review insights and produce a structured critique.

    When ``FEATURE_CRITIC`` is disabled, the node auto-approves all insights
    and passes through immediately.

    Reads:  state['insight_report'], state['profile_result']
    Writes: state['critique'] — {approved: bool, issues: list[str], revised_insights: list}
    """
    if not flags.critic_enabled:
        return {"critique": {"approved": True, "issues": [], "revised_insights": []}}

    insight_report = state.get("insight_report", {})
    profile = state.get("profile_result", {})

    try:
        from backend.agents.critic_agent import CriticAgent
        from backend.infrastructure.llm.bedrock.bedrock_converse_adapter import (
            BedrockConverseAdapter,
        )

        agent = CriticAgent(llm=BedrockConverseAdapter())
        critique = await agent.run(
            insight_report=insight_report,
            profile=profile,
        )
        logger.info(
            "critic_node_complete",
            approved=critique.get("approved"),
            issues=len(critique.get("issues", [])),
        )
        return {"critique": critique}

    except Exception as exc:
        logger.warning("critic_node_failed_auto_approve", error=str(exc))
        return {
            "critique": {"approved": True, "issues": [], "error": str(exc)},
            "errors": [f"CriticNode: {exc}"],
        }
