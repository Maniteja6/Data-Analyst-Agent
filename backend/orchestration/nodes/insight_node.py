"""InsightNode — calls the InsightAgent to produce the insight report."""
from __future__ import annotations

import structlog
from backend.orchestration.state.pipeline_state import PipelineState

logger = structlog.get_logger(__name__)


async def insight_node(state: PipelineState) -> dict:
    """LangGraph node: generate business insights from all agent outputs.

    Reads:  state['agent_results'], state['profile_result'],
            state['cleaning_result'], state['critique'] (on retry)
    Writes: state['insight_report'] — InsightReport.to_dict()
    """
    ctx           = state.get("context", {})
    agent_results = state.get("agent_results", {})
    profile       = state.get("profile_result", {})
    critique      = state.get("critique", {})
    meta          = state.get("metadata", {}) or {}
    revision_round = meta.get("revision_round", 0)

    try:
        from backend.agents.insight_agent import InsightAgent
        from backend.infrastructure.llm.bedrock.bedrock_converse_adapter import BedrockConverseAdapter
        from backend.domain.analytics.services.data_quality_scorer import DataQualityScorer

        agent = InsightAgent(llm=BedrockConverseAdapter())
        report = await agent.run(
            agent_results=agent_results,
            profile=profile,
            dataset_id=ctx.get("dataset_id", ""),
            session_id=ctx.get("session_id", ""),
            previous_critique=critique if revision_round > 0 else None,
        )

        meta["revision_round"] = revision_round + 1
        logger.info(
            "insight_node_complete",
            insights=len(report.get("insights", [])),
            round=revision_round + 1,
        )
        return {"insight_report": report, "metadata": meta}

    except Exception as exc:
        logger.error("insight_node_failed", error=str(exc))
        return {"insight_report": {}, "errors": [f"InsightNode: {exc}"]}
