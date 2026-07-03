"""ProfilingCompleted domain event."""
from __future__ import annotations

from dataclasses import dataclass

from backend.shared.domain_event import DomainEvent


@dataclass(frozen=True)
class ProfilingCompleted(DomainEvent):
    """Emitted by AnalysisSession.complete_profiling().

    Consumed by:
    - DatasetUploadedConsumer — triggers the cleaning pipeline
    - WebSocket gateway — sends a progress update to the browser
    - RAGAgent — triggers async vector indexing of the schema chunks
    """

    dataset_id:         str   = ""
    session_id:         str   = ""
    row_count:          int   = 0
    column_count:       int   = 0
    completeness_score: float = 1.0

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({
            "dataset_id":         self.dataset_id,
            "session_id":         self.session_id,
            "row_count":          self.row_count,
            "column_count":       self.column_count,
            "completeness_score": self.completeness_score,
        })
        return base
