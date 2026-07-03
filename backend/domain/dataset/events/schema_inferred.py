"""SchemaInferred domain event."""
from __future__ import annotations

from dataclasses import dataclass

from backend.shared.domain_event import DomainEvent


@dataclass(frozen=True)
class SchemaInferred(DomainEvent):
    """Emitted by ``Dataset.complete_schema_inference()`` after the Schema Agent runs.

    Kafka topic: ``dataset.schema-inferred``

    Consumed by:
    - ``on_schema_inferred`` event handler — triggers async RAG indexing:
      the schema chunks are embedded via Titan and upserted into Qdrant so
      that chat queries can retrieve relevant column descriptions.
    - WebSocket gateway — sends a progress update to the upload progress bar.

    Emitted mid-profiling (before PROFILED state) because schema indexing
    can run in parallel with the full statistical profiling.

    Attributes:
        dataset_id:   UUID of the Dataset.
        column_count: Number of columns found.
        row_count:    Number of rows in the inference sample.
    """

    dataset_id:   str = ""
    column_count: int = 0
    row_count:    int = 0

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({
            "dataset_id":   self.dataset_id,
            "column_count": self.column_count,
            "row_count":    self.row_count,
        })
        return base
