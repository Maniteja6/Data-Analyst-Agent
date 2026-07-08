"""UploadDatasetCommand — input DTO for the UploadDatasetUseCase."""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO


@dataclass(frozen=True)
class UploadDatasetCommand:
    """All data required to upload and register a new dataset.

    Attributes:
        filename:     Original filename supplied by the user.
        file_obj:     Readable binary file-like object (from the HTTP request).
        size_bytes:   Pre-computed file size in bytes (validated before reading).
        mime_type:    Detected or user-provided MIME type.
        project_id:   Optional workspace project to associate the dataset with.
        correlation_id: Request-scoped tracing ID from ``X-Correlation-ID`` header.
    """

    filename: str
    file_obj: BinaryIO
    size_bytes: int
    mime_type: str
    project_id: str | None = None
    correlation_id: str = ""
