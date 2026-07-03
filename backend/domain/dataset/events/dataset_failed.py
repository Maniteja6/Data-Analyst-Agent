"""DatasetFailed domain event."""
from __future__ import annotations

from dataclasses import dataclass

from backend.shared.domain_event import DomainEvent


@dataclass(frozen=True)
class DatasetFailed(DomainEvent):
    """Emitted by ``Dataset.mark_failed()`` when processing cannot continue.

    Kafka topic: ``dataset.failed`` (routed via the error dead-letter topic)

    Consumed by:
    - WebSocket gateway — sends ``job.progress`` event with status=failed
      so the browser shows the error state on the UploadProgress component
    - Alerting/monitoring — increments the ``datapilot_datasets_failed_total``
      Prometheus counter

    Attributes:
        dataset_id: UUID of the failed Dataset.
        reason:     Human-readable description of the failure, stored in
                    ``Dataset.error_message`` and shown to the user.
    """

    dataset_id: str = ""
    reason:     str = ""

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({"dataset_id": self.dataset_id, "reason": self.reason})
        return base
