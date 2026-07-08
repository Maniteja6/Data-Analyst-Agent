"""Domain event handlers — react to aggregate events and update real-time state.

Each handler is called by a KafkaConsumer after consuming a domain event.
All handlers call ICacheService.publish_json() to push updates to the
Redis pub/sub channel which the Socket.IO bridge forwards to browsers.

    on_dataset_uploaded          → Redis job status 0%; push dataset:processing
    on_schema_inferred           → trigger RAG chunk indexing
    on_profiling_completed       → Redis job status 30%
    on_analytics_completed       → enqueue agent Celery task; job status 65%
    on_insight_report_generated  → invalidate insight cache; job status 100%;
                                    publish analysis.complete to Socket.IO
"""

from backend.application.event_handlers.on_analytics_completed import on_analytics_completed
from backend.application.event_handlers.on_dataset_uploaded import on_dataset_uploaded
from backend.application.event_handlers.on_insight_report_generated import (
    on_insight_report_generated,
)
from backend.application.event_handlers.on_profiling_completed import on_profiling_completed
from backend.application.event_handlers.on_schema_inferred import on_schema_inferred

__all__ = [
    "on_dataset_uploaded",
    "on_schema_inferred",
    "on_profiling_completed",
    "on_analytics_completed",
    "on_insight_report_generated",
]
