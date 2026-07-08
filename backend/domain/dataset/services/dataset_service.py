"""DatasetService — domain service for Dataset validation and MIME inference."""

from __future__ import annotations

import os

from backend.domain.dataset.exceptions import (
    EmptyFileError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from backend.domain.dataset.value_objects.mime_type import EXTENSION_MIME_MAP

# Default 2 GB limit — overridden by Settings.max_upload_size_bytes at runtime
DEFAULT_MAX_SIZE_BYTES = 2 * 1024 * 1024 * 1024

# Minimum file size to be considered non-empty
MIN_SIZE_BYTES = 1


class DatasetService:
    """Domain service containing business rules that don't belong on the
    Dataset aggregate itself because they require external context
    (file size limits from Settings, extension mapping, etc.).

    Used by ``UploadDatasetUseCase`` before creating a Dataset aggregate.
    """

    def __init__(self, max_size_bytes: int = DEFAULT_MAX_SIZE_BYTES) -> None:
        self._max_size_bytes = max_size_bytes

    # ── Validation ────────────────────────────────────────────────────────

    def validate_file(self, filename: str, size_bytes: int) -> None:
        """Run all pre-upload validations and raise on the first failure.

        Checks (in order):
        1. File must not be empty.
        2. Extension must be in the supported list.
        3. File must not exceed the size limit.

        Args:
            filename:   Original filename including extension.
            size_bytes: File size in bytes.

        Raises:
            EmptyFileError:          size_bytes == 0
            UnsupportedFileTypeError: extension not in EXTENSION_MIME_MAP
            FileTooLargeError:       size_bytes > max_size_bytes
        """
        if size_bytes < MIN_SIZE_BYTES:
            raise EmptyFileError(filename)

        ext = os.path.splitext(filename.lower())[1]
        if ext not in EXTENSION_MIME_MAP:
            raise UnsupportedFileTypeError(filename)

        if size_bytes > self._max_size_bytes:
            raise FileTooLargeError(size_bytes, self._max_size_bytes)

    # ── MIME inference ────────────────────────────────────────────────────

    def infer_mime_from_extension(self, filename: str) -> str:
        """Return the MIME type string for the given filename extension.

        Falls back to ``'application/octet-stream'`` for unknown extensions
        (this case should not be reached if ``validate_file`` is called first).

        Args:
            filename: Original filename (e.g. ``'sales_data.xlsx'``).

        Returns:
            MIME type string (e.g. ``'application/vnd.openxmlformats-...'``).
        """
        ext = os.path.splitext(filename.lower())[1]
        return EXTENSION_MIME_MAP.get(ext, "application/octet-stream")

    # ── Storage key generation ────────────────────────────────────────────

    @staticmethod
    def build_storage_key(dataset_id: str, filename: str) -> str:
        """Build the S3/MinIO object key for a dataset file.

        Format: ``datasets/<dataset_id>/<original_filename>``

        The dataset_id prefix ensures each upload lives in its own
        S3 "folder", preventing filename collisions across users.

        Args:
            dataset_id: UUID of the Dataset aggregate.
            filename:   Original filename to preserve the extension.

        Returns:
            S3 object key string, e.g. ``'datasets/abc-123/sales_q3.csv'``.
        """
        safe_name = os.path.basename(filename)  # strip any path traversal
        return f"datasets/{dataset_id}/{safe_name}"

    # ── Duplicate detection ───────────────────────────────────────────────

    @staticmethod
    def is_duplicate(checksum: str, existing_checksum: str | None) -> bool:
        """Return True when two checksums match, indicating a duplicate upload."""
        if not existing_checksum:
            return False
        return checksum.lower() == existing_checksum.lower()
