"""on_insight_report_generated — cache invalidation and final job completion."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from backend.application.ports.cache_port import ICacheService

logger = structlog.get_logger(__name__)


async def on_insight_report_generated(event: dict, cache: ICacheService | None = None) -> None:
    """Invalidate the insight cache and update the job status to complete.

    Called when InsightReportGenerated is received. This causes the next
    ``GET /api/v1/insights/<dataset_id>`` to fetch fresh data from Postgres
    rather than serving a stale cache entry.

    Args:
        event: InsightReportGenerated.to_dict() payload.
        cache: ICacheService.
    """
    dataset_id = event.get("dataset_id", "")
    correlation_id = event.get("correlation_id", "")
    insight_count = event.get("insight_count", 0)

    if cache:
        # Delete stale insight cache
        await cache.invalidate_insights(dataset_id)

        # Update job status to complete
        if correlation_id:
            await cache.cache_job_status(
                job_id=correlation_id,
                status="complete",
                progress=100,
                step="Analysis complete",
                extra={
                    "dataset_id": dataset_id,
                    "insight_count": str(insight_count),
                },
            )

        # Publish analysis.complete event → WebSocket gateway
        await cache.publish_json(
            f"dataset:{dataset_id}",
            {
                "type": "analysis.complete",
                "dataset_id": dataset_id,
                "insight_count": insight_count,
                "has_forecasts": event.get("has_forecasts", False),
            },
        )

    logger.info(
        "on_insight_report_generated",
        dataset_id=dataset_id,
        insight_count=insight_count,
    )
