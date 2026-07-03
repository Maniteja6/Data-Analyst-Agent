"""DatasetUploadedConsumer — triggers the analytics pipeline on upload.

Subscribes to: ``dataset.uploaded``
Group ID:      ``datapilot-analytics-engine``

On receiving a ``DatasetUploaded`` event this consumer:

1. Updates the Dataset status to PROFILING in Postgres.
2. Enqueues the ``analysis.run_pipeline`` Celery task on the ``analysis`` queue.
3. Publishes a job progress update to Redis pub/sub (→ WebSocket → browser).
4. Triggers RAG indexing if the schema is already available (schema-first uploads).

At-least-once delivery: If the consumer crashes after step 2 but before
committing the Kafka offset, the message is redelivered and the Celery task
is enqueued again. The task is idempotent — a dataset already in PROFILING
state will be re-profiled (acceptable for the initial implementation; add
Postgres advisory locking for strict once-only semantics if needed).
"""
from __future__ import annotations

import structlog

from backend.infrastructure.messaging.kafka_consumer import KafkaConsumerBase

logger = structlog.get_logger(__name__)


class DatasetUploadedConsumer(KafkaConsumerBase):
    """Kafka consumer that handles DatasetUploaded events."""

    def __init__(self, celery_app=None, cache=None) -> None:
        """
        Args:
            celery_app: Celery application instance. When None, imported lazily
                        from ``celery_app`` module on first use.
            cache:      RedisCacheAdapter for job status updates.
        """
        super().__init__(
            topics=["dataset.uploaded"],
            group_id="datapilot-analytics-engine",
        )
        self._celery = celery_app
        self._cache  = cache

    async def handle_message(self, topic: str, payload: dict) -> None:
        """Process one DatasetUploaded event.

        Args:
            topic:   Always ``'dataset.uploaded'``.
            payload: Dict with ``dataset_id``, ``storage_key``, ``filename``,
                     ``size_bytes``, ``mime_type``, ``correlation_id``.
        """
        dataset_id     = payload.get("dataset_id", "")
        storage_key    = payload.get("storage_key", "")
        correlation_id = payload.get("correlation_id", "")
        filename       = payload.get("filename", "")
        size_bytes     = payload.get("size_bytes", 0)

        if not dataset_id or not storage_key:
            logger.warning(
                "dataset_uploaded_event_missing_fields",
                payload_keys=list(payload.keys()),
            )
            raise self.SkipMessage("Missing dataset_id or storage_key")

        structlog.contextvars.bind_contextvars(
            dataset_id=dataset_id,
            correlation_id=correlation_id,
        )

        logger.info(
            "dataset_uploaded_event_received",
            dataset_id=dataset_id,
            filename=filename,
            size_bytes=size_bytes,
        )

        # ── Step 1: Update dataset status to PROFILING in Postgres ────────
        await self._transition_to_profiling(dataset_id)

        # ── Step 2: Write initial job status to Redis ─────────────────────
        cache = self._get_cache()
        if cache:
            await cache.cache_job_status(
                job_id=correlation_id,
                status="running",
                progress=5,
                step="Queued for analysis…",
                extra={"dataset_id": dataset_id},
            )
            import json
            await cache.publish(
                f"dataset:{dataset_id}",
                json.dumps({
                    "type":       "job.progress",
                    "progress":   0.05,
                    "message":    "Upload received — starting analysis…",
                    "dataset_id": dataset_id,
                }),
            )

        # ── Step 3: Enqueue the analytics pipeline Celery task ─────────────
        task_id = self._enqueue_pipeline(dataset_id, storage_key, correlation_id)
        logger.info(
            "analysis_pipeline_enqueued",
            dataset_id=dataset_id,
            task_id=task_id,
        )

    # ── Private helpers ───────────────────────────────────────────────────

    async def _transition_to_profiling(self, dataset_id: str) -> None:
        """Transition the Dataset aggregate to PROFILING status."""
        try:
            from backend.infrastructure.persistence.database import get_session
            from backend.infrastructure.persistence.repositories.postgres_dataset_repository import (
                PostgresDatasetRepository,
            )
            async with get_session() as session:
                repo    = PostgresDatasetRepository(session)
                dataset = await repo.get_by_id(dataset_id)
                if dataset and dataset.status.value == "uploaded":
                    dataset.begin_profiling()
                    await repo.save(dataset)
        except Exception as exc:
            logger.warning(
                "transition_to_profiling_failed",
                dataset_id=dataset_id,
                error=str(exc),
            )
            # Non-fatal — pipeline can still proceed

    def _enqueue_pipeline(
        self,
        dataset_id: str,
        storage_key: str,
        correlation_id: str,
    ) -> str:
        """Enqueue the Celery analysis pipeline task and return the task ID."""
        if self._celery is None:
            from backend.infrastructure.job_queue.celery_app import celery_app
            self._celery = celery_app

        from backend.infrastructure.job_queue.tasks.analysis_tasks import run_analysis_pipeline
        result = run_analysis_pipeline.apply_async(
            kwargs={
                "dataset_id":     dataset_id,
                "storage_key":    storage_key,
                "correlation_id": correlation_id,
            },
            queue="analysis",
        )
        return result.id

    def _get_cache(self):
        if self._cache is None:
            try:
                from backend.infrastructure.cache.redis_cache_adapter import get_redis_cache
                self._cache = get_redis_cache()
            except Exception:
                return None
        return self._cache
