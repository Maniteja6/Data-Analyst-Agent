"""Dataset bounded context — upload, schema inference, lifecycle management."""
"""Dataset bounded context — owns the upload lifecycle state machine.

Aggregate: Dataset (uploaded → profiling → profiled → cleaning → ready | failed)
Service:   DatasetService (validation, MIME inference, storage key builder)
Events:    DatasetUploaded, DatasetReady, DatasetFailed
"""
from backend.domain.dataset.entities.dataset        import Dataset
from backend.domain.dataset.value_objects.dataset_status import DatasetStatus
from backend.domain.dataset.services.dataset_service    import DatasetService

__all__ = ["Dataset", "DatasetStatus", "DatasetService"]
