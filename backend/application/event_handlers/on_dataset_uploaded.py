"""on_dataset_uploaded — handles DatasetUploaded domain event."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from backend.application.ports.cache_port import ICacheService

logger = structlog.get_logger(__name__)


async def on_dataset_uploaded(event: dict, cache: ICacheService | None = None) -> None:
    """Write initial job status to Redis when a dataset is uploaded.

    This handler is invoked by the use case immediately after
    publishing the DatasetUploaded event. It primes the job status
    cache so the frontend can show a spinner immediately without
    waiting for the Celery task to start.

    Args:
        event: DatasetUploaded.to_dict() payload.
        cache: ICacheService — Redis cache adapter.
    """
    dataset_id = event.get("dataset_id", "")
    correlation_id = event.get("correlation_id", "")

    if cache and correlation_id:
        await cache.cache_job_status(
            job_id=correlation_id,
            status="pending",
            progress=0,
            step="Upload received — queued for analysis…",
            extra={"dataset_id": dataset_id},
        )

    logger.info(
        "on_dataset_uploaded",
        dataset_id=dataset_id,
        filename=event.get("filename"),
        size_bytes=event.get("size_bytes"),
    )
