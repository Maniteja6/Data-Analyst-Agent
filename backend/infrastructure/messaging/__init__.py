"""Kafka event bus and consumers — async aiokafka.

KafkaEventBus:  aiokafka producer; publish(event) + publish_batch(events).
                EVENT_TOPIC_MAP: 12 event types → 8 Kafka topics.
KafkaConsumerBase: base class with auto-reconnect + offset commit on success.
3 consumers:    DatasetUploadedConsumer, AnalyticsCompletedConsumer,
                InsightGeneratedConsumer — each runs as an asyncio.Task.
"""

from backend.infrastructure.messaging.kafka_consumer import KafkaConsumerBase
from backend.infrastructure.messaging.kafka_event_bus import KafkaEventBus

__all__ = ["KafkaEventBus", "KafkaConsumerBase"]
