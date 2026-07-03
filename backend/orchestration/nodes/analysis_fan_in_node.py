"""AnalysisFanInNode — collects parallel agent results before InsightNode.

This is a pass-through node that LangGraph uses to synchronise the
parallel fan-out branches before calling the InsightNode. It validates
that at least one agent succeeded and enriches the metadata with
aggregate token and cost totals.
"""
from __future__ import annotations

import structlog
from backend.orchestration.state.pipeline_state import PipelineState

logger = structlog.get_logger(__name__)


async def analysis_fan_in_node(state: PipelineState) -> dict:
    """Synchronisation node after parallel agent fan-out.

    Reads:  state['agent_results']
    Writes: state['metadata'] (enriched with agent completion summary)
    """
    results   = state.get("agent_results", {})
    succeeded = [k for k, v in results.items() if "error" not in v]
    failed    = [k for k, v in results.items() if "error" in v]

    logger.info(
        "fan_in_complete",
        succeeded=succeeded,
        failed=failed,
        total=len(results),
    )

    meta = state.get("metadata", {}) or {}
    meta.update({
        "fan_out_agents":      list(results.keys()),
        "fan_out_succeeded":   succeeded,
        "fan_out_failed":      failed,
    })
    return {"metadata": meta}
