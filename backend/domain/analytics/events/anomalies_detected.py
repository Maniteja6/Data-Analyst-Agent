"""AnomaliesDetected domain event."""
from __future__ import annotations

from dataclasses import dataclass

from backend.shared.domain_event import DomainEvent


@dataclass(frozen=True)
class AnomaliesDetected(DomainEvent):
    """Emitted when anomaly detection finds at least one anomaly.

    Consumed by:
    - InsightGeneratedConsumer — invalidates the insight cache
    - WebSocket gateway — pushes an anomaly alert badge to the browser
    """

    dataset_id:    str = ""
    session_id:    str = ""
    anomaly_count: int = 0

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({
            "dataset_id":    self.dataset_id,
            "session_id":    self.session_id,
            "anomaly_count": self.anomaly_count,
        })
        return base
