"""Dataset bounded context exceptions."""
from __future__ import annotations

from backend.shared.exceptions import DomainException, ValidationException


class DatasetException(DomainException):
    """Base exception for the dataset bounded context."""


class InvalidStatusTransitionError(DatasetException):
    """Raised when a Dataset aggregate is asked to move to an unreachable state.

    Example: trying to transition from READY → PROFILING is not allowed
    because READY is a terminal success state.
    """

    def __init__(self, current: object, target: object) -> None:
        super().__init__(
            f"Cannot transition Dataset from '{current}' to '{target}'.",
            code="INVALID_DATASET_STATUS_TRANSITION",
        )
        self.current = current
        self.target  = target


class DatasetNotFoundException(DatasetException):
    """Raised when a requested Dataset does not exist in the repository."""

    def __init__(self, dataset_id: str) -> None:
        super().__init__(
            f"Dataset '{dataset_id}' not found.",
            code="DATASET_NOT_FOUND",
        )
        self.dataset_id = dataset_id


class DuplicateDatasetError(DatasetException):
    """Raised when a file with an identical SHA-256 checksum already exists
    for the same project, preventing duplicate storage costs.
    """

    def __init__(self, checksum: str, existing_id: str) -> None:
        super().__init__(
            f"A dataset with checksum '{checksum[:12]}…' already exists "
            f"(id={existing_id}). Duplicate uploads are not permitted.",
            code="DUPLICATE_DATASET",
        )
        self.checksum    = checksum
        self.existing_id = existing_id


class UnsupportedFileTypeError(ValidationException):
    """Raised when the uploaded file has an extension that DataPilot cannot process."""

    SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls", ".parquet", ".json", ".jsonl"}

    def __init__(self, filename: str) -> None:
        import os
        ext = os.path.splitext(filename)[1].lower() or "(none)"
        super().__init__(
            "filename",
            f"Extension '{ext}' is not supported. "
            f"Supported formats: {', '.join(sorted(self.SUPPORTED_EXTENSIONS))}",
        )
        self.filename  = filename
        self.extension = ext


class FileTooLargeError(ValidationException):
    """Raised when the uploaded file exceeds the configured size limit."""

    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        size_mb = size_bytes / (1024 ** 2)
        max_mb  = max_bytes  / (1024 ** 2)
        super().__init__(
            "file_size",
            f"Upload size {size_mb:.1f} MB exceeds the {max_mb:.0f} MB limit.",
        )
        self.size_bytes = size_bytes
        self.max_bytes  = max_bytes


class EmptyFileError(ValidationException):
    """Raised when the uploaded file has zero bytes."""

    def __init__(self, filename: str) -> None:
        super().__init__("file", f"'{filename}' is empty (0 bytes).")
        self.filename = filename


class SchemaInferenceError(DatasetException):
    """Raised when schema inference cannot determine column types."""

    def __init__(self, dataset_id: str, reason: str) -> None:
        super().__init__(
            f"Schema inference failed for dataset '{dataset_id}': {reason}",
            code="SCHEMA_INFERENCE_FAILED",
        )
        self.dataset_id = dataset_id
        self.reason     = reason
