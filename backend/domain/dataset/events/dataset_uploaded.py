"""DatasetUploaded domain event."""
from __future__ import annotations

from dataclasses import dataclass

from backend.shared.domain_event import DomainEvent


@dataclass(frozen=True)
class DatasetUploaded(DomainEvent):
    """Emitted by ``Dataset.create()`` immediately after the file is stored.

    Kafka topic: ``dataset.uploaded``

    Consumed by:
    - ``DatasetUploadedConsumer`` — enqueues ``run_analysis_pipeline`` Celery task
    - WebSocket gateway — notifies the browser that processing has started
    - ``on_dataset_uploaded`` event handler — updates the job status cache

    Attributes:
        dataset_id:   UUID of the newly created Dataset aggregate.
        storage_key:  S3/MinIO object key for the raw file bytes.
        filename:     Original filename supplied by the user.
        size_bytes:   File size at upload time.
        mime_type:    Detected MIME type string.
    """

    dataset_id:  str = ""
    storage_key: str = ""
    filename:    str = ""
    size_bytes:  int = 0
    mime_type:   str = ""

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({
            "dataset_id":  self.dataset_id,
            "storage_key": self.storage_key,
            "filename":    self.filename,
            "size_bytes":  self.size_bytes,
            "mime_type":   self.mime_type,
        })
        return base
