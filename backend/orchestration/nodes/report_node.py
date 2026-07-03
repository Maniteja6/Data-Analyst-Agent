"""ReportNode — finalises the InsightReport and persists it to Postgres."""
from __future__ import annotations

import structlog
from backend.orchestration.state.pipeline_state import PipelineState

logger = structlog.get_logger(__name__)


async def report_node(state: PipelineState) -> dict:
    """LangGraph node: apply Critic revisions, persist, and cache the report.

    Reads:  state['insight_report'], state['critique'], state['context']
    Writes: state['final_report'] — the persisted InsightReport.to_dict()
    """
    ctx            = state.get("context", {})
    insight_report = state.get("insight_report", {})
    critique       = state.get("critique", {})

    # Apply any critic revisions to the insight list
    if critique.get("revised_insights"):
        insight_report = {
            **insight_report,
            "insights": critique["revised_insights"],
        }

    try:
        from backend.agents.recommendation_agent import RecommendationAgent
        from backend.infrastructure.llm.bedrock.bedrock_converse_adapter import BedrockConverseAdapter

        rec_agent = RecommendationAgent(llm=BedrockConverseAdapter())
        insight_report = await rec_agent.run(insight_report=insight_report)

    except Exception as exc:
        logger.warning("recommendation_agent_failed", error=str(exc))

    # Persist to Postgres
    try:
        from backend.infrastructure.persistence.database import get_session
        from backend.infrastructure.persistence.repositories.postgres_insight_repository import (
            PostgresInsightRepository,
        )
        from backend.domain.insight.entities.insight_report import InsightReport

        report_entity = InsightReport.create(
            session_id=ctx.get("session_id", ""),
            dataset_id=ctx.get("dataset_id", ""),
        )
        report_entity.executive_summary = insight_report.get("executive_summary", "")

        async with get_session() as db_session:
            repo = PostgresInsightRepository(db_session)
            await repo.save(report_entity)

    except Exception as exc:
        logger.warning("report_persist_failed", error=str(exc))

    # Cache in Redis
    try:
        from backend.infrastructure.cache.redis_cache_adapter import get_redis_cache
        cache = get_redis_cache()
        await cache.set_json(
            f"insights:{ctx.get('dataset_id', '')}",
            insight_report,
            ttl=86400,
        )
    except Exception as exc:
        logger.warning("report_cache_failed", error=str(exc))

    logger.info(
        "report_node_complete",
        dataset_id=ctx.get("dataset_id"),
        insights=len(insight_report.get("insights", [])),
    )
    return {"final_report": insight_report}
