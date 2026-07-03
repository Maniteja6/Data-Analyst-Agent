"""AnalyticsCompletedConsumer — triggers the AI agent pipeline after analytics.

Subscribes to: ``analytics.profiling-complete``, ``analytics.cleaning-complete``
Group ID:      ``datapilot-analytics-engine``

This consumer bridges the deterministic analytics pipeline (profiling, cleaning,
anomaly detection) and the AI agent pipeline (LangGraph DAG). It acts only on
``CLEANING_COMPLETE`` stage events — the final stage before agents are needed.

Separation of concerns:
    - The analytics pipeline runs on ``analysis`` Celery workers (high CPU).
    - The agent pipeline runs on ``agents`` Celery workers (Bedrock API-bound).
    - This consumer decouples them via the event bus — neither pipeline knows
      about the other's queue or task names.

Idempotency:
    The consumer checks that the Dataset is in READY status before enqueuing
    agents. If the dataset is already READY (pipeline was re-triggered), the
    agent task is not re-enqueued to avoid duplicate insight reports.
"""
from __future__ import annotations

import structlog

from backend.infrastructure.messaging.kafka_consumer import KafkaConsumerBase

logger = structlog.get_logger(__name__)

# Only trigger agents on the final cleaning stage
TRIGGER_STAGE = "CLEANING_COMPLETE"


class AnalyticsCompletedConsumer(KafkaConsumerBase):
    """Triggers the AI agent pipeline when analytics finishes."""

    def __init__(self, celery_app=None, cache=None) -> None:
        super().__init__(
            topics=[
                "analytics.profiling-complete",
                "analytics.cleaning-complete",
            ],
            group_id="datapilot-analytics-engine",
        )
        self._celery = celery_app
        self._cache  = cache

    async def handle_message(self, topic: str, payload: dict) -> None:
        dataset_id     = payload.get("dataset_id", "")
        session_id     = payload.get("session_id", "")
        correlation_id = payload.get("correlation_id", "")
        stage          = payload.get("stage", "")

        if not dataset_id:
            raise self.SkipMessage("Missing dataset_id in analytics completed event")

        structlog.contextvars.bind_contextvars(
            dataset_id=dataset_id,
            session_id=session_id,
            stage=stage,
        )

        logger.info(
            "analytics_completed_event_received",
            topic=topic,
            dataset_id=dataset_id,
            stage=stage,
        )

        # ── Profiling complete: update progress bar ────────────────────────
        if topic == "analytics.profiling-complete":
            await self._update_progress(
                correlation_id, dataset_id, 35, "Profiling complete — cleaning data…"
            )
            return

        # ── Cleaning complete: trigger AI agents ──────────────────────────
        if topic == "analytics.cleaning-complete":
            await self._update_progress(
                correlation_id, dataset_id, 65, "Cleaning complete — running AI analysis…"
            )

            # Guard: don't re-enqueue if dataset is already READY
            if await self._dataset_is_ready(dataset_id):
                logger.info("dataset_already_ready_skip_agents", dataset_id=dataset_id)
                return

            task_id = self._enqueue_agents(dataset_id, session_id, correlation_id)
            logger.info(
                "agent_pipeline_enqueued",
                dataset_id=dataset_id,
                session_id=session_id,
                task_id=task_id,
            )

    # ── Private helpers ───────────────────────────────────────────────────

    async def _update_progress(
        self,
        correlation_id: str,
        dataset_id: str,
        progress: int,
        step: str,
    ) -> None:
        """Write progress to Redis and publish to WebSocket channel."""
        cache = self._get_cache()
        if not cache:
            return
        try:
            await cache.cache_job_status(
                job_id=correlation_id,
                status="running",
                progress=progress,
                step=step,
                extra={"dataset_id": dataset_id},
            )
            import json
            await cache.publish(
                f"dataset:{dataset_id}",
                json.dumps({
                    "type":       "job.progress",
                    "progress":   progress / 100,
                    "message":    step,
                    "dataset_id": dataset_id,
                }),
            )
        except Exception as exc:
            logger.warning("progress_update_failed", error=str(exc))

    async def _dataset_is_ready(self, dataset_id: str) -> bool:
        """Return True when the dataset is already in READY status."""
        try:
            from backend.infrastructure.persistence.database import get_session
            from backend.infrastructure.persistence.repositories.postgres_dataset_repository import (
                PostgresDatasetRepository,
            )
            async with get_session() as session:
                repo    = PostgresDatasetRepository(session)
                dataset = await repo.get_by_id(dataset_id)
                return dataset is not None and dataset.status.value == "ready"
        except Exception:
            return False

    def _enqueue_agents(
        self,
        dataset_id: str,
        session_id: str,
        correlation_id: str,
    ) -> str:
        if self._celery is None:
            from backend.infrastructure.job_queue.celery_app import celery_app
            self._celery = celery_app

        from backend.infrastructure.job_queue.tasks.agent_tasks import run_agent_pipeline
        result = run_agent_pipeline.apply_async(
            kwargs={
                "dataset_id":     dataset_id,
                "session_id":     session_id,
                "correlation_id": correlation_id,
            },
            queue="agents",
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
