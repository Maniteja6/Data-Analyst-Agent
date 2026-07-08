"""InsightReportGenerated domain event."""

from __future__ import annotations

from dataclasses import dataclass

from backend.shared.domain_event import DomainEvent


@dataclass(frozen=True)
class InsightReportGenerated(DomainEvent):
    """Emitted by InsightReport.create() once a report has been persisted.

    Published to the ``insight.report-generated`` Kafka topic (see
    EVENT_TOPIC_MAP in kafka_event_bus.py). Consumed by:
    - WebSocket gateway — notifies the browser the report is ready
    - ReportAgent — triggers async PDF generation
    """

    report_id: str = ""
    dataset_id: str = ""
    session_id: str = ""
    insight_count: int = 0
    has_forecasts: bool = False

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update(
            {
                "report_id": self.report_id,
                "dataset_id": self.dataset_id,
                "session_id": self.session_id,
                "insight_count": self.insight_count,
                "has_forecasts": self.has_forecasts,
            }
        )
        return base
