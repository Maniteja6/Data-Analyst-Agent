"""AnalysisFanOutNode — dispatches parallel analysis agents.

This node receives the cleaned profile and fires multiple agent tasks
concurrently using asyncio.gather. Each agent writes its result into
``state['agent_results']`` under its agent name key.

Agents run in parallel:
  - SQLAgent        — aggregation queries for KPI extraction
  - RAGAgent        — schema chunk indexing (if FEATURE_RAG enabled)
  - AnomalyAgent    — runs all four detectors
  - ForecastAgent   — only when has_time_series condition is 'yes'
  - MLAgent         — only when FEATURE_ML_AGENT and enough numeric columns
"""

from __future__ import annotations

import asyncio

import structlog
from backend.config.feature_flags import flags
from backend.orchestration.state.pipeline_state import PipelineState

logger = structlog.get_logger(__name__)


async def analysis_fan_out_node(state: PipelineState) -> dict:
    """Run parallel analysis agents and collect their results."""
    ctx = state.get("context", {})
    profile = state.get("profile_result", {})
    has_datetime = state.get("metadata", {}).get("has_time_series", False)

    tasks: dict[str, asyncio.Task] = {}

    # Always-on agents
    tasks["sql"] = asyncio.create_task(_run_sql_agent(ctx, profile))
    tasks["anomaly"] = asyncio.create_task(_run_anomaly_agent(ctx, profile))

    # Feature-flagged agents
    if flags.rag_enabled:
        tasks["rag"] = asyncio.create_task(_run_rag_agent(ctx, profile))
    if has_datetime and flags.forecasting_enabled:
        tasks["forecast"] = asyncio.create_task(_run_forecast_agent(ctx, profile))
    if flags.ml_agent_enabled:
        tasks["ml"] = asyncio.create_task(_run_ml_agent(ctx, profile))

    # Wait for all agents with individual error isolation
    agent_results: dict[str, dict] = {}
    errors: list[str] = []
    for name, task in tasks.items():
        try:
            agent_results[name] = await task
            logger.info("fan_out_agent_complete", agent=name)
        except Exception as exc:
            logger.warning("fan_out_agent_failed", agent=name, error=str(exc))
            errors.append(f"FanOut.{name}: {exc}")
            agent_results[name] = {"error": str(exc)}

    return {"agent_results": agent_results, "errors": errors}


# ── Individual agent runners ──────────────────────────────────────────────


async def _run_sql_agent(ctx: dict, profile: dict) -> dict:
    from backend.agents.sql_agent import SQLAgent
    from backend.analytics_engine.ingestion.file_reader import FileReader
    from backend.analytics_engine.sql_engine.duckdb_manager import DuckDBManager
    from backend.infrastructure.llm.bedrock.bedrock_converse_adapter import BedrockConverseAdapter

    reader = FileReader()
    df = await reader.read(ctx["storage_key"])
    agent = SQLAgent(llm=BedrockConverseAdapter(), db=DuckDBManager())
    return await agent.run(df=df, profile=profile, dataset_id=ctx.get("dataset_id", ""))


async def _run_anomaly_agent(ctx: dict, profile: dict) -> dict:
    from backend.agents.anomaly_agent import AnomalyAgent
    from backend.analytics_engine.ingestion.file_reader import FileReader

    reader = FileReader()
    df = await reader.read(ctx["storage_key"])
    agent = AnomalyAgent()
    return await agent.run(df=df, profile=profile)


async def _run_rag_agent(ctx: dict, profile: dict) -> dict:
    from backend.agents.rag_agent import RAGAgent
    from backend.infrastructure.vector_store.collection_manager import CollectionManager

    agent = RAGAgent(collection_manager=CollectionManager())
    return await agent.run(profile=profile, dataset_id=ctx.get("dataset_id", ""))


async def _run_forecast_agent(ctx: dict, profile: dict) -> dict:
    from backend.agents.forecast_agent import ForecastAgent
    from backend.analytics_engine.ingestion.file_reader import FileReader
    from backend.infrastructure.llm.bedrock.bedrock_converse_adapter import BedrockConverseAdapter

    reader = FileReader()
    df = await reader.read(ctx["storage_key"])
    agent = ForecastAgent(llm=BedrockConverseAdapter())
    return await agent.run(df=df, profile=profile)


async def _run_ml_agent(ctx: dict, profile: dict) -> dict:
    from backend.agents.ml_agent import MLAgent
    from backend.analytics_engine.ingestion.file_reader import FileReader

    reader = FileReader()
    df = await reader.read(ctx["storage_key"])
    agent = MLAgent()
    return await agent.run(df=df, profile=profile)
