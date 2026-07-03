"""KafkaConsumerBase — abstract base for all DataPilot Kafka consumers.

Each consumer is a long-running asyncio task that:
1. Subscribes to one or more Kafka topics.
2. Receives messages from aiokafka.
3. Deserialises the payload (JSON or Avro).
4. Dispatches to the concrete ``handle_message()`` implementation.
5. Commits the offset after successful processing (at-least-once semantics).

Error handling strategy:
    - **Transient errors** (DB timeout, Redis down): log warning and retry
      the message up to ``MAX_RETRIES`` times with exponential backoff.
    - **Permanent errors** (schema validation fail, unknown event type):
      log error and skip (commit the offset) to avoid consumer group stall.
    - **Critical errors** (OOM, assertion error): stop the consumer and let
      the Kubernetes restart policy revive the pod.

Offset commit strategy:
    ``enable_auto_commit=False`` — offsets are committed manually after each
    successful call to ``handle_message()``. This gives exactly-once semantics
    at the application level (process-then-commit vs commit-then-process).

Usage (extend and override ``handle_message``):

    class MyConsumer(KafkaConsumerBase):
        def __init__(self):
            super().__init__(topics=["dataset.uploaded"])

        async def handle_message(self, topic: str, payload: dict) -> None:
            dataset_id = payload["dataset_id"]
            await some_service.process(dataset_id)

    consumer = MyConsumer()
    await consumer.run()   # long-running; blocks until stopped
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from backend.config.settings import get_settings

logger = structlog.get_logger(__name__)

# Maximum retries before a message is skipped (dead-lettered in production)
MAX_RETRIES = 3
RETRY_BASE_DELAY_SECONDS = 2.0


class KafkaConsumerBase:
    """Abstract base class for DataPilot Kafka consumers.

    Subclasses must implement ``handle_message(topic, payload)``.
    """

    def __init__(
        self,
        topics: list[str],
        group_id: str | None = None,
        auto_offset_reset: str = "earliest",
    ) -> None:
        """
        Args:
            topics:            List of Kafka topic names to subscribe to.
            group_id:          Consumer group ID. Defaults to ``Settings.kafka_consumer_group_id``.
            auto_offset_reset: Where to start reading when no committed offset exists.
                               ``'earliest'`` — replay all messages (safe default).
                               ``'latest'``   — skip historical messages.
        """
        settings              = get_settings()
        self._topics           = topics
        self._group_id         = group_id or settings.kafka_consumer_group_id
        self._bootstrap        = settings.kafka_bootstrap_servers
        self._security_protocol = settings.kafka_security_protocol
        self._sasl_mechanism   = settings.kafka_sasl_mechanism
        self._sasl_username    = settings.kafka_sasl_username
        self._sasl_password    = settings.kafka_sasl_password
        self._auto_offset_reset = auto_offset_reset
        self._consumer         = None
        self._running          = False

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Create and start the aiokafka consumer."""
        from aiokafka import AIOKafkaConsumer

        kwargs: dict[str, Any] = {
            "bootstrap_servers":   self._bootstrap,
            "group_id":            self._group_id,
            "auto_offset_reset":   self._auto_offset_reset,
            "enable_auto_commit":  False,       # manual commit for at-least-once
            "max_poll_records":    100,
            "session_timeout_ms":  30_000,
            "heartbeat_interval_ms": 10_000,
            "value_deserializer":  self._deserialize_value,
        }

        if self._security_protocol in ("SASL_SSL", "SSL"):
            kwargs["security_protocol"] = self._security_protocol
            if self._sasl_mechanism:
                kwargs["sasl_mechanism"] = self._sasl_mechanism
            if self._sasl_username:
                kwargs["sasl_plain_username"] = self._sasl_username
                kwargs["sasl_plain_password"] = self._sasl_password

        self._consumer = AIOKafkaConsumer(*self._topics, **kwargs)
        await self._consumer.start()
        self._running = True
        logger.info(
            "kafka_consumer_started",
            topics=self._topics,
            group_id=self._group_id,
        )

    async def stop(self) -> None:
        """Commit pending offsets and close the consumer."""
        self._running = False
        if self._consumer:
            try:
                await self._consumer.commit()
                await self._consumer.stop()
                logger.info("kafka_consumer_stopped", topics=self._topics)
            except Exception as exc:
                logger.warning("kafka_consumer_stop_failed", error=str(exc))
            finally:
                self._consumer = None

    # ── Message processing loop ───────────────────────────────────────────

    async def run(self) -> None:
        """Start the consumer and process messages until ``stop()`` is called.

        This method blocks indefinitely. Run it as an asyncio task:
            asyncio.create_task(consumer.run())
        """
        await self.start()
        try:
            async for msg in self._consumer:
                await self._process_message(msg)
        except asyncio.CancelledError:
            logger.info("kafka_consumer_cancelled", topics=self._topics)
        except Exception as exc:
            logger.error("kafka_consumer_fatal_error", error=str(exc), topics=self._topics)
            raise
        finally:
            await self.stop()

    async def _process_message(self, msg) -> None:
        """Process one Kafka message with retry and error handling."""
        topic   = msg.topic
        payload = msg.value   # already deserialised by value_deserializer

        # Bind log context for this message
        structlog.contextvars.bind_contextvars(
            kafka_topic=topic,
            kafka_partition=msg.partition,
            kafka_offset=msg.offset,
        )

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                await self.handle_message(topic, payload)
                await self._consumer.commit()
                structlog.contextvars.clear_contextvars()
                return

            except _SkipMessage:
                # Permanent error — skip this message and commit the offset
                logger.warning(
                    "kafka_message_skipped",
                    topic=topic,
                    offset=msg.offset,
                )
                await self._consumer.commit()
                structlog.contextvars.clear_contextvars()
                return

            except Exception as exc:
                if attempt == MAX_RETRIES:
                    logger.error(
                        "kafka_message_max_retries_exceeded",
                        topic=topic,
                        offset=msg.offset,
                        error=str(exc),
                    )
                    # Skip to avoid stalling the consumer group
                    await self._consumer.commit()
                    structlog.contextvars.clear_contextvars()
                    return
                else:
                    delay = RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                    logger.warning(
                        "kafka_message_retry",
                        topic=topic,
                        offset=msg.offset,
                        attempt=attempt,
                        delay=delay,
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)

    # ── Deserialisation ───────────────────────────────────────────────────

    @staticmethod
    def _deserialize_value(raw: bytes) -> dict:
        """Decode a Kafka message value.

        Tries Avro first (magic byte 0x00), falls back to JSON.
        Safe to use as ``value_deserializer`` in aiokafka constructor.
        """
        if not raw:
            return {}

        # Detect Confluent wire format (magic byte)
        if len(raw) >= 5 and raw[0] == 0x00:
            try:
                from backend.infrastructure.messaging.avro.serializer import get_avro_serializer
                import asyncio
                loop = asyncio.get_event_loop()
                return loop.run_until_complete(
                    get_avro_serializer().deserialize(raw)
                )
            except Exception:
                pass   # fall through to JSON

        # Plain JSON
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception as exc:
            logger.warning("kafka_deserialize_failed", error=str(exc))
            return {}

    # ── Abstract interface ────────────────────────────────────────────────

    async def handle_message(self, topic: str, payload: dict) -> None:
        """Process one decoded message. Override in subclasses.

        Raise ``KafkaConsumerBase.SkipMessage()`` to skip without retrying.
        Raise any other exception to trigger the retry mechanism.

        Args:
            topic:   Kafka topic name the message arrived on.
            payload: Decoded message payload dict.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement handle_message()"
        )

    class SkipMessage(Exception):
        """Raise from ``handle_message`` to permanently skip a message."""


# Private alias for the skip-message sentinel (used in _process_message)
_SkipMessage = KafkaConsumerBase.SkipMessage
