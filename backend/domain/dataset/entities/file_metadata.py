"""FileMetadata value-like entity — physical properties of an uploaded file."""
from __future__ import annotations

from dataclasses import dataclass

from backend.shared.entity import Entity


@dataclass
class FileMetadata(Entity):
    """Captures the physical properties of a file at upload time.

    FileMetadata is an entity (has an ID for tracking) rather than a pure
    value object because it participates in audit queries (e.g. "which files
    were uploaded with checksum X?"). However, its fields are effectively
    immutable after creation.

    Attributes:
        original_filename: Filename as supplied by the user or browser,
                           including extension. Not used as a storage key —
                           that is the responsibility of the storage adapter.
        size_bytes:        File size in bytes, captured before upload.
        mime_type:         Detected or inferred MIME type string.
        storage_key:       Object key in S3 / local storage where the file
                           is persisted, e.g. ``'datasets/<id>/sales_q3.csv'``.
        checksum_sha256:   SHA-256 hex digest of the raw file bytes.
                           Used for deduplication and integrity verification.
        encoding:          Detected character encoding (UTF-8, ISO-8859-1, etc.).
                           Relevant only for CSV/TSV files.
        detected_delimiter: CSV delimiter character (``','``, ``'\\t'``, ``';'``).
                           None for non-CSV formats.
    """

    original_filename:  str
    size_bytes:         int
    mime_type:          str
    storage_key:        str
    checksum_sha256:    str | None  = None
    encoding:           str | None  = None
    detected_delimiter: str | None  = None

    # ── Derived helpers ───────────────────────────────────────────────────

    @property
    def size_mb(self) -> float:
        """File size in megabytes (2 decimal places)."""
        return round(self.size_bytes / (1024 ** 2), 2)

    @property
    def extension(self) -> str:
        """Lowercase file extension including the dot, e.g. ``'.csv'``."""
        import os
        return os.path.splitext(self.original_filename)[1].lower()

    @property
    def is_large_file(self) -> bool:
        """True when the file exceeds 100 MB — triggers streaming processing."""
        return self.size_bytes > 100 * 1024 * 1024

    def to_dict(self) -> dict:
        return {
            "id":                 self.id,
            "original_filename":  self.original_filename,
            "size_bytes":         self.size_bytes,
            "size_mb":            self.size_mb,
            "mime_type":          self.mime_type,
            "storage_key":        self.storage_key,
            "checksum_sha256":    self.checksum_sha256,
            "encoding":           self.encoding,
            "detected_delimiter": self.detected_delimiter,
            "extension":          self.extension,
        }
