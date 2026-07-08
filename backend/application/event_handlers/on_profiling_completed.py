"""on_profiling_completed — updates dataset status and publishes progress."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from backend.application.ports.cache_port import ICacheService
    from backend.domain.dataset.repositories.dataset_repository import DatasetRepository

logger = structlog.get_logger(__name__)


async def on_profiling_completed(
    event: dict,
    cache: ICacheService | None = None,
    dataset_repo: DatasetRepository | None = None,
) -> None:
    """React to ProfilingCompleted by updating the job status cache.

    Args:
        event:       ProfilingCompleted.to_dict() payload.
        cache:       ICacheService for job status updates.
        dataset_repo: DatasetRepository for transitioning status.
    """
    dataset_id = event.get("dataset_id", "")
    session_id = event.get("session_id", "")
    correlation_id = event.get("correlation_id", "")

    if cache and correlation_id:
        await cache.cache_job_status(
            job_id=correlation_id,
            status="running",
            progress=30,
            step=(
                f"Profiling complete — {event.get('column_count', '?')} columns analysed. Cleaning…"
            ),
            extra={"dataset_id": dataset_id, "session_id": session_id},
        )
        await cache.publish_json(
            f"dataset:{dataset_id}",
            {
                "type": "job.progress",
                "progress": 0.30,
                "message": "Profiling complete",
                "dataset_id": dataset_id,
            },
        )

    logger.info(
        "on_profiling_completed",
        dataset_id=dataset_id,
        row_count=event.get("row_count"),
        completeness=event.get("completeness_score"),
    )
