"""MimeType value object — validated MIME type for uploaded files."""
from __future__ import annotations

from dataclasses import dataclass

from backend.shared.value_object import ValueObject


# Supported MIME types and their canonical extensions
SUPPORTED_MIME_TYPES: dict[str, str] = {
    "text/csv":                                                       ".csv",
    "text/tab-separated-values":                                      ".tsv",
    "text/plain":                                                     ".txt",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel":                                       ".xls",
    "application/octet-stream":                                       ".parquet",  # Parquet has no standard MIME
    "application/json":                                               ".json",
    "application/x-ndjson":                                          ".jsonl",
}

# Extension → MIME type mapping used during upload validation
EXTENSION_MIME_MAP: dict[str, str] = {
    ".csv":     "text/csv",
    ".tsv":     "text/tab-separated-values",
    ".txt":     "text/plain",
    ".xlsx":    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls":     "application/vnd.ms-excel",
    ".parquet": "application/octet-stream",
    ".pq":      "application/octet-stream",
    ".json":    "application/json",
    ".jsonl":   "application/x-ndjson",
}


@dataclass(frozen=True)
class MimeType(ValueObject):
    """Validated MIME type for an uploaded dataset file.

    Enforces that only supported formats can be uploaded.
    The ``FileReader`` uses ``MimeType`` to select the correct
    parser (CSV, Excel, Parquet, JSON).

    Example::

        mt = MimeType("text/csv")
        assert mt.extension == ".csv"
        assert mt.is_csv

        MimeType("image/png")   # raises ValueError
    """

    value: str

    def _validate(self) -> None:
        if self.value not in SUPPORTED_MIME_TYPES:
            supported = ", ".join(sorted(SUPPORTED_MIME_TYPES))
            raise ValueError(
                f"MIME type '{self.value}' is not supported. "
                f"Supported types: {supported}"
            )

    # ── Factory ───────────────────────────────────────────────────────────

    @classmethod
    def from_extension(cls, filename: str) -> "MimeType":
        """Infer MimeType from a filename's extension.

        Args:
            filename: Original filename including extension (e.g. ``'sales_q3.csv'``).

        Raises:
            ValueError: If the extension is not in ``EXTENSION_MIME_MAP``.
        """
        import os
        ext = os.path.splitext(filename)[1].lower()
        mime = EXTENSION_MIME_MAP.get(ext)
        if not mime:
            from backend.domain.dataset.exceptions import UnsupportedFileTypeError
            raise UnsupportedFileTypeError(filename)
        return cls(value=mime)

    # ── Type checks ───────────────────────────────────────────────────────

    @property
    def extension(self) -> str:
        """Returns the canonical file extension for this MIME type (e.g. ``'.csv'``)."""
        return SUPPORTED_MIME_TYPES[self.value]

    @property
    def is_csv(self) -> bool:
        return self.value in ("text/csv", "text/tab-separated-values", "text/plain")

    @property
    def is_excel(self) -> bool:
        return self.value in (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
        )

    @property
    def is_parquet(self) -> bool:
        return self.value == "application/octet-stream"

    @property
    def is_json(self) -> bool:
        return self.value in ("application/json", "application/x-ndjson")

    def __str__(self) -> str:
        return self.value
