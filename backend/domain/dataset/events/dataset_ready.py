"""DatasetReady domain event."""

from __future__ import annotations

from dataclasses import dataclass

from backend.shared.domain_event import DomainEvent


@dataclass(frozen=True)
class DatasetReady(DomainEvent):
    """Emitted by ``Dataset.mark_ready()`` when the full pipeline completes.

    Kafka topic: ``dataset.ready``

    Consumed by:
    - WebSocket gateway — triggers ``analysis.complete`` event to the browser,
      which invalidates React Query caches and refreshes all panels
    - ``on_insight_report_generated`` event handler — clears the insight cache
      so the next GET returns fresh data

    This event is the signal that the dataset is available for:
    - Chat queries (ChatPanel activates)
    - Insight viewing (InsightList populates)
    - Export (ExportResultsPage enables download buttons)
    """

    dataset_id: str = ""

    def to_dict(self) -> dict:
        base = super().to_dict()
        base["dataset_id"] = self.dataset_id
        return base
