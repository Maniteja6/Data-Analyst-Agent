"""CleaningCompleted domain event."""

from __future__ import annotations

from dataclasses import dataclass

from backend.shared.domain_event import DomainEvent


@dataclass(frozen=True)
class CleaningCompleted(DomainEvent):
    """Emitted by AnalysisSession.complete_cleaning().

    Consumed by:
    - AnalyticsCompletedConsumer — triggers the AI agent pipeline
    - WebSocket gateway — sends a progress update to the browser
    """

    dataset_id: str = ""
    session_id: str = ""
    rows_before: int = 0
    rows_after: int = 0

    @property
    def rows_removed(self) -> int:
        return max(0, self.rows_before - self.rows_after)

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update(
            {
                "dataset_id": self.dataset_id,
                "session_id": self.session_id,
                "rows_before": self.rows_before,
                "rows_after": self.rows_after,
                "rows_removed": self.rows_removed,
            }
        )
        return base
