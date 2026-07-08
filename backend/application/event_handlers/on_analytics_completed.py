"""on_analytics_completed — enqueues the AI agent pipeline after cleaning."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from backend.application.ports.cache_port import ICacheService
    from backend.application.ports.job_port import IJobService

logger = structlog.get_logger(__name__)


async def on_analytics_completed(
    event: dict, job_service: IJobService | None = None, cache: ICacheService | None = None
) -> None:
    """Enqueue the AI agent pipeline when the analytics pipeline finishes.

    This handler responds to CleaningCompleted events. It bridges the
    deterministic analytics pipeline and the LLM agent pipeline.

    Args:
        event:       CleaningCompleted.to_dict() payload.
        job_service: IJobService for Celery task enqueueing.
        cache:       ICacheService for progress updates.
    """
    dataset_id = event.get("dataset_id", "")
    session_id = event.get("session_id", "")
    correlation_id = event.get("correlation_id", "")

    if cache and correlation_id:
        await cache.cache_job_status(
            job_id=correlation_id,
            status="running",
            progress=65,
            step="Data cleaning complete — running AI analysis…",
            extra={"dataset_id": dataset_id},
        )

    if job_service and dataset_id:
        try:
            task_id = job_service.enqueue_agents(
                dataset_id=dataset_id,
                session_id=session_id,
                correlation_id=correlation_id,
            )
            logger.info("agents_enqueued", dataset_id=dataset_id, task_id=task_id)
        except Exception as exc:
            logger.error("agent_enqueue_failed", dataset_id=dataset_id, error=str(exc))
