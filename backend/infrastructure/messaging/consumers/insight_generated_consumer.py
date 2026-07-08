"""InsightGeneratedConsumer — cache invalidation and WebSocket notification.

Subscribes to: ``insight.report-generated``, ``anomaly.detected``
Group ID:      ``datapilot-insight-cache``

This consumer handles the final stage of the analysis pipeline by:

1. **Invalidating the Redis insight cache** — deletes ``insights:<dataset_id>``
   so the next GET /insights/<dataset_id> returns fresh data from Postgres.

2. **Publishing to the WebSocket channel** — sends ``analysis.complete`` to
   the ``dataset:<dataset_id>`` Redis pub/sub channel. The Socket.IO server
   listens to this channel and emits ``analysis:complete`` to all clients in
   the ``dataset:<dataset_id>`` room, causing React Query to refetch all panels.

3. **Updating the final job status** — writes ``status=complete, progress=100``
   to the Redis job status hash so the browser's upload progress bar reaches 100%.

4. **Anomaly alerts** — for ``anomaly.detected`` events with CRITICAL or HIGH
   severity, emits an ``anomaly:alert`` WebSocket event for the browser
   notification badge without requiring a full page refresh.

Group ID note:
    A separate ``datapilot-insight-cache`` consumer group is used so that
    the cache invalidation and WebSocket notification are independent of the
    analytics pipeline consumer group. This means both groups receive the event
    simultaneously (Kafka fan-out by consumer group).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import structlog
from backend.infrastructure.messaging.kafka_consumer import KafkaConsumerBase

if TYPE_CHECKING:
    from backend.infrastructure.cache.redis_cache_adapter import RedisCacheAdapter

logger = structlog.get_logger(__name__)


class InsightGeneratedConsumer(KafkaConsumerBase):
    """Invalidates caches and notifies WebSocket clients on insight generation."""

    def __init__(self, cache: RedisCacheAdapter | None = None) -> None:
        super().__init__(
            topics=[
                "insight.report-generated",
                "anomaly.detected",
            ],
            group_id="datapilot-insight-cache",
        )
        self._cache = cache

    async def handle_message(self, topic: str, payload: dict) -> None:
        dataset_id = payload.get("dataset_id", "")
        payload.get("correlation_id", "")
        event_type = payload.get("event_type", "")

        if not dataset_id:
            raise self.SkipMessageError("Missing dataset_id")

        structlog.contextvars.bind_contextvars(
            dataset_id=dataset_id,
            event_type=event_type,
            topic=topic,
        )

        cache = self._get_cache()

        if topic == "insight.report-generated":
            await self._handle_insight_generated(payload, cache)

        elif topic == "anomaly.detected":
            await self._handle_anomaly_detected(payload, cache)

    # ── Topic handlers ────────────────────────────────────────────────────

    async def _handle_insight_generated(
        self, payload: dict, cache: RedisCacheAdapter | None
    ) -> None:
        """Invalidate insight cache and push analysis.complete to WebSocket."""
        dataset_id = payload.get("dataset_id", "")
        correlation_id = payload.get("correlation_id", "")
        insight_count = payload.get("insight_count", 0)
        has_forecasts = payload.get("has_forecasts", False)

        # ── 1. Invalidate the Redis insight cache ─────────────────────────
        if cache:
            try:
                await cache.delete(f"insights:{dataset_id}")
                logger.info(
                    "insight_cache_invalidated",
                    dataset_id=dataset_id,
                    insight_count=insight_count,
                )
            except Exception as exc:
                logger.warning("insight_cache_invalidation_failed", error=str(exc))

        # ── 2. Publish analysis.complete to WebSocket channel ─────────────
        if cache:
            try:
                await cache.publish(
                    f"dataset:{dataset_id}",
                    json.dumps(
                        {
                            "type": "analysis.complete",
                            "dataset_id": dataset_id,
                            "insight_count": insight_count,
                            "has_forecasts": has_forecasts,
                        }
                    ),
                )
                logger.info("analysis_complete_published", dataset_id=dataset_id)
            except Exception as exc:
                logger.warning("websocket_publish_failed", error=str(exc))

        # ── 3. Update final job status to complete ────────────────────────
        if cache and correlation_id:
            try:
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
            except Exception as exc:
                logger.warning("job_status_update_failed", error=str(exc))

        logger.info(
            "insight_report_processed",
            dataset_id=dataset_id,
            insight_count=insight_count,
        )

    async def _handle_anomaly_detected(
        self, payload: dict, cache: RedisCacheAdapter | None
    ) -> None:
        """Push anomaly alert to WebSocket for CRITICAL/HIGH severity anomalies."""
        dataset_id = payload.get("dataset_id", "")
        severity = payload.get("severity", "low")
        column_name = payload.get("column_name", "")
        anomaly_type = payload.get("anomaly_type", "")
        alert_id = payload.get("alert_id", "")

        # Only push real-time notifications for high-priority anomalies
        if severity not in ("critical", "high"):
            return

        if cache:
            try:
                await cache.publish(
                    f"dataset:{dataset_id}",
                    json.dumps(
                        {
                            "type": "anomaly.alert",
                            "dataset_id": dataset_id,
                            "alert_id": alert_id,
                            "severity": severity,
                            "column_name": column_name,
                            "anomaly_type": anomaly_type,
                        }
                    ),
                )
                logger.info(
                    "anomaly_alert_published",
                    dataset_id=dataset_id,
                    severity=severity,
                    column_name=column_name,
                )
            except Exception as exc:
                logger.warning("anomaly_alert_publish_failed", error=str(exc))

    # ── Private helpers ───────────────────────────────────────────────────

    def _get_cache(self) -> RedisCacheAdapter | None:
        if self._cache is None:
            try:
                from backend.infrastructure.cache.redis_cache_adapter import get_redis_cache

                self._cache = get_redis_cache()
            except Exception:
                return None
        return self._cache
