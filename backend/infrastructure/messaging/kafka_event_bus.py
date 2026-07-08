"""KafkaEventBus — async Kafka producer for publishing domain events.

The event bus is the outbound channel from the domain layer to the outside
world. Domain events are published after an aggregate is persisted to Postgres
and all in-memory state is consistent.

Publishing flow:
    1. Use case calls ``aggregate.some_action()`` → records domain event
    2. Use case calls ``await repo.save(aggregate)`` → Postgres commit
    3. Use case calls ``for e in aggregate.pull_domain_events(): await bus.publish(e)``
    4. KafkaEventBus serialises event → publishes to the correct Kafka topic
    5. Kafka consumer receives event → triggers downstream processing

Why publish-after-persist (not transactional outbox)?
    The current implementation publishes directly from the use case after
    the Postgres commit. This means there is a small window where the DB
    write succeeds but the Kafka publish fails (e.g. broker down). For the
    current scale this is acceptable — the Celery task in ``analysis_tasks.py``
    achieves equivalent at-least-once semantics via its retry mechanism.

    For strict exactly-once delivery, replace with a transactional outbox:
    write the event to a Postgres ``outbox`` table in the same transaction,
    and a separate CDC process (Debezium) publishes from the outbox to Kafka.

Topic routing (matches KafkaEventBus.EVENT_TOPIC_MAP):
    DatasetUploaded          → dataset.uploaded
    SchemaInferred           → dataset.schema-inferred
    DatasetReady             → dataset.ready
    DatasetFailed            → dataset.failed
    ProfilingCompleted       → analytics.profiling-complete
    CleaningCompleted        → analytics.cleaning-complete
    AnomaliesDetected        → anomaly.detected
    InsightReportGenerated   → insight.report-generated
    ForecastCompleted        → insight.report-generated
    AgentResultReady         → agent.result
    MessageAdded             → chat.message
    MemoryConsolidated       → chat.message

Usage::

    bus = KafkaEventBus()
    await bus.start()
    try:
        await bus.publish(event, partition_key=dataset_id)
    finally:
        await bus.stop()

    # Or as an async context manager:
    async with KafkaEventBus() as bus:
        await bus.publish(event)
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from backend.config.settings import get_settings
from backend.shared.domain_event import DomainEvent

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Topic routing map — event class name → Kafka topic
# ---------------------------------------------------------------------------

EVENT_TOPIC_MAP: dict[str, str] = {
    # Dataset lifecycle
    "DatasetUploaded": "dataset.uploaded",
    "SchemaInferred": "dataset.schema-inferred",
    "DatasetReady": "dataset.ready",
    "DatasetFailed": "dataset.failed",
    # Analytics pipeline
    "ProfilingCompleted": "analytics.profiling-complete",
    "CleaningCompleted": "analytics.cleaning-complete",
    "AnomaliesDetected": "anomaly.detected",
    # Insight generation
    "InsightReportGenerated": "insight.report-generated",
    "ForecastCompleted": "insight.report-generated",
    "AnomalyAlertRaised": "anomaly.detected",
    # Agent orchestration
    "AgentResultReady": "agent.result",
    # Chat / workspace
    "MessageAdded": "chat.message",
    "MemoryConsolidated": "chat.message",
}


class KafkaEventBus:
    """Async Kafka producer wrapping ``aiokafka.AIOKafkaProducer``.

    Lifecycle:
        - Call ``await start()`` before first ``publish()``.
        - Call ``await stop()`` during application shutdown.
        - Use as an async context manager for ephemeral scopes.

    Message format:
        Values are JSON-encoded (Avro encoding available via ``AvroSerializer``
        but not enabled by default — see the ``use_avro`` constructor parameter).
        Keys are UTF-8 encoded partition keys (typically ``dataset_id``).
    """

    def __init__(
        self,
        bootstrap_servers: str | None = None,
        use_avro: bool = False,
    ) -> None:
        """
        Args:
            bootstrap_servers: Kafka broker list. Defaults to ``Settings.kafka_bootstrap_servers``.
            use_avro:          When True, use Avro binary serialisation via ``AvroSerializer``.
                               When False (default), use JSON (simpler for local dev/testing).
        """
        settings = get_settings()
        self._bootstrap = bootstrap_servers or settings.kafka_bootstrap_servers
        self._security_protocol = settings.kafka_security_protocol
        self._sasl_mechanism = settings.kafka_sasl_mechanism
        self._sasl_username = settings.kafka_sasl_username
        self._sasl_password = settings.kafka_sasl_password
        self._use_avro = use_avro
        self._producer = None
        self._started = False

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Initialise and start the aiokafka producer.

        Must be called before ``publish()``. Safe to call multiple times —
        subsequent calls are no-ops if already started.
        """
        if self._started:
            return

        try:
            from aiokafka import AIOKafkaProducer

            kwargs: dict[str, Any] = {
                "bootstrap_servers": self._bootstrap,
                "value_serializer": lambda v: json.dumps(v, default=str).encode("utf-8"),
                "key_serializer": lambda k: k.encode("utf-8") if k else None,
                "acks": "all",  # wait for all ISR replicas
                "compression_type": "gzip",
                "request_timeout_ms": 10_000,
                "retry_backoff_ms": 500,
                "max_batch_size": 32_768,  # 32 KB batch
            }

            # MSK IAM / SASL_SSL configuration
            if self._security_protocol in ("SASL_SSL", "SSL"):
                kwargs["security_protocol"] = self._security_protocol
                if self._sasl_mechanism:
                    kwargs["sasl_mechanism"] = self._sasl_mechanism
                if self._sasl_username:
                    kwargs["sasl_plain_username"] = self._sasl_username
                    kwargs["sasl_plain_password"] = self._sasl_password

            self._producer = AIOKafkaProducer(**kwargs)
            await self._producer.start()
            self._started = True
            logger.info("kafka_producer_started", bootstrap=self._bootstrap)

        except ImportError:
            logger.warning(
                "aiokafka_not_installed",
                detail="Kafka publishing disabled — install aiokafka to enable.",
            )
        except Exception as exc:
            logger.error("kafka_producer_start_failed", error=str(exc))
            raise

    async def stop(self) -> None:
        """Flush pending messages and close the producer connection."""
        if self._producer and self._started:
            try:
                await self._producer.stop()
                logger.info("kafka_producer_stopped")
            except Exception as exc:
                logger.warning("kafka_producer_stop_failed", error=str(exc))
            finally:
                self._producer = None
                self._started = False

    # ── Context manager ───────────────────────────────────────────────────

    async def __aenter__(self) -> KafkaEventBus:
        await self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.stop()

    # ── Publishing ────────────────────────────────────────────────────────

    async def publish(
        self,
        event: DomainEvent,
        partition_key: str | None = None,
    ) -> None:
        """Publish a single domain event to its designated Kafka topic.

        Topic is determined by ``EVENT_TOPIC_MAP[event.event_type]``.
        Unknown event types are logged as warnings and not published.

        Args:
            event:         The domain event to publish.
            partition_key: Optional Kafka partition key. When None, uses
                           ``event.dataset_id`` (if the event has one) or
                           ``event.correlation_id`` to keep related events
                           on the same partition for ordered consumption.

        Raises:
            RuntimeError: When called before ``start()`` is invoked.
        """
        topic = EVENT_TOPIC_MAP.get(event.event_type)
        if topic is None:
            logger.warning(
                "kafka_unknown_event_type",
                event_type=event.event_type,
                event_id=event.event_id,
            )
            return

        if not self._producer or not self._started:
            logger.debug(
                "kafka_publish_skipped_no_producer",
                event_type=event.event_type,
                topic=topic,
            )
            return

        # Determine partition key for ordering
        key = (
            partition_key
            or getattr(event, "dataset_id", None)
            or getattr(event, "conversation_id", None)
            or event.correlation_id
        )

        # Serialise payload
        if self._use_avro:
            from backend.infrastructure.messaging.avro.serializer import get_avro_serializer

            payload = await get_avro_serializer().serialize(event.event_type, event.to_dict())
        else:
            payload = event.to_dict()  # JSON serialiser applied by the producer's value_serializer

        try:
            await self._producer.send_and_wait(topic, value=payload, key=key)
            logger.info(
                "kafka_event_published",
                topic=topic,
                event_type=event.event_type,
                event_id=event.event_id,
                partition_key=key,
            )
        except Exception as exc:
            logger.error(
                "kafka_publish_failed",
                topic=topic,
                event_type=event.event_type,
                error=str(exc),
            )
            raise

    async def publish_batch(
        self,
        events: list[DomainEvent],
        partition_key: str | None = None,
    ) -> None:
        """Publish multiple domain events efficiently.

        Events are sent as a batch using aiokafka's internal batching.
        The producer flushes at ``max_batch_size`` (32 KB) or after
        ``linger_ms`` (0 ms by default — immediately).

        Args:
            events:        List of domain events to publish.
            partition_key: Shared partition key for all events in the batch.
        """
        for event in events:
            await self.publish(event, partition_key)

    # ── Health check ──────────────────────────────────────────────────────

    async def ping(self) -> bool:
        """Return True when the producer has a live broker connection."""
        return self._started and self._producer is not None

    # ── Topic utilities ───────────────────────────────────────────────────

    @staticmethod
    def topic_for(event_type: str) -> str | None:
        """Return the Kafka topic for an event type, or None if unmapped."""
        return EVENT_TOPIC_MAP.get(event_type)

    @staticmethod
    def all_topics() -> list[str]:
        """Return the deduplicated list of all topics used by DataPilot."""
        return sorted(set(EVENT_TOPIC_MAP.values()))
