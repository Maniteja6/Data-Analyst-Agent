"""Kafka consumer implementations."""

from backend.infrastructure.messaging.consumers.analytics_completed_consumer import (
    AnalyticsCompletedConsumer,
)
from backend.infrastructure.messaging.consumers.dataset_uploaded_consumer import (
    DatasetUploadedConsumer,
)
from backend.infrastructure.messaging.consumers.insight_generated_consumer import (
    InsightGeneratedConsumer,
)

__all__ = [
    "DatasetUploadedConsumer",
    "AnalyticsCompletedConsumer",
    "InsightGeneratedConsumer",
]
