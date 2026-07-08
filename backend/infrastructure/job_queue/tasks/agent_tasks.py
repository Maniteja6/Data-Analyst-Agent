"""Celery tasks for the AI agent pipeline.

Queue: ``agents``
Typical worker flags: ``--concurrency=4`` (I/O-bound; Bedrock API calls)

The agent pipeline is triggered after the analytics pipeline completes
(either via the ``AnalyticsCompletedConsumer`` or directly from the
``RunAnalysisUseCase``). It runs the full LangGraph DAG:

    PlannerAgent → DAGExecutor (parallel fan-out)
      → SchemaAgent, SQLAgent, ForecastAgent, MLAgent (parallel)
      → InsightAgent → CriticAgent → RecommendationAgent → ReportAgent

Results are stored in the ``insight_reports`` table and the Redis insight
cache is written for fast dashboard loads.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

import structlog
from backend.infrastructure.job_queue.celery_app import celery_app

if TYPE_CHECKING:
    from celery import Task

logger = structlog.get_logger(__name__)


@celery_app.task(
    bind=True,
    name="agents.run_pipeline",
    max_retries=2,
    default_retry_delay=60,
    acks_late=True,
    soft_time_limit=240,
    time_limit=300,
)
def run_agent_pipeline(
    self: Task,
    dataset_id: str,
    session_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Execute the full AI agent DAG for a completed analytics session.

    Args:
        dataset_id:     Source dataset UUID.
        session_id:     Analysis session UUID (from the analytics pipeline).
        correlation_id: Request-scoped tracing ID.

    Returns:
        Summary: ``{dataset_id, session_id, insight_count, status}``.
    """
    logger.info(
        "agent_pipeline_start",
        task_id=self.request.id,
        dataset_id=dataset_id,
        session_id=session_id,
    )
    start = time.monotonic()

    try:
        result = asyncio.run(
            _run_agents_async(
                task=self,
                dataset_id=dataset_id,
                session_id=session_id,
                correlation_id=correlation_id,
            )
        )
        duration = round(time.monotonic() - start, 2)
        logger.info(
            "agent_pipeline_complete",
            dataset_id=dataset_id,
            duration_seconds=duration,
            **result,
        )
        return result

    except Exception as exc:
        logger.error(
            "agent_pipeline_failed",
            dataset_id=dataset_id,
            error=str(exc),
            attempt=self.request.retries + 1,
        )
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1)) from exc
        raise


async def _run_agents_async(
    task: Task,
    dataset_id: str,
    session_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Core async agent pipeline logic."""
    from backend.infrastructure.cache.redis_cache_adapter import get_redis_cache
    from backend.infrastructure.persistence.database import get_session
    from backend.infrastructure.persistence.repositories.postgres_dataset_repository import (
        PostgresDatasetRepository,
    )
    from backend.orchestration.graphs.analysis_pipeline_graph import build_analysis_graph
    from backend.orchestration.state.pipeline_state import PipelineState

    cache = get_redis_cache()

    # Load dataset to get storage_key and schema
    async with get_session() as db_session:
        repo = PostgresDatasetRepository(db_session)
        dataset = await repo.get_by_id(dataset_id)
        if not dataset:
            logger.warning("dataset_not_found_for_agents", dataset_id=dataset_id)
            return {"dataset_id": dataset_id, "status": "skipped", "reason": "dataset_not_found"}

        storage_key = dataset.storage_key
        schema = dataset.schema_json or {}

    # Build initial pipeline state
    initial_state = PipelineState(
        context={
            "session_id": session_id,
            "dataset_id": dataset_id,
            "correlation_id": correlation_id,
            "storage_key": storage_key,
            "schema": schema,
        }
    )

    # Publish progress — agent phase starting
    import json

    await cache.publish(
        f"dataset:{dataset_id}",
        json.dumps(
            {
                "type": "job.progress",
                "progress": 0.0,
                "message": "Running AI analysis…",
                "dataset_id": dataset_id,
            }
        ),
    )

    # Execute the LangGraph DAG
    graph = build_analysis_graph()
    final_state = await graph.ainvoke(initial_state)
    insight_report = final_state.get("context", {}).get("insight_report", {})
    insight_count = (
        len(insight_report.get("insights", [])) if isinstance(insight_report, dict) else 0
    )

    # Cache the insight report for fast dashboard loads
    if insight_report:
        await cache.set_json(
            f"insights:{dataset_id}",
            insight_report,
            ttl=86400,
        )

    # Publish completion event → WebSocket gateway
    await cache.publish(
        f"dataset:{dataset_id}",
        json.dumps(
            {
                "type": "analysis.complete",
                "dataset_id": dataset_id,
                "insight_count": insight_count,
            }
        ),
    )

    return {
        "dataset_id": dataset_id,
        "session_id": session_id,
        "insight_count": insight_count,
        "status": "complete",
    }
