"""FormatDetector — sniffs file format and encoding from bytes or path.

Used by FileReader before opening a file to determine the correct parser
and any format-specific parameters (delimiter, encoding, sheet name).

Detection strategy (in order):
  1. File extension (fastest, usually reliable)
  2. Magic bytes / file header (reliable for binary formats)
  3. Heuristic CSV sniffing via ``csv.Sniffer`` on the first 4KB
"""

from __future__ import annotations

import csv
import os

import structlog

logger = structlog.get_logger(__name__)

EXTENSION_FORMAT_MAP = {
    ".csv": "csv",
    ".tsv": "csv",
    ".txt": "csv",
    ".xlsx": "excel",
    ".xls": "excel",
    ".xlsm": "excel",
    ".parquet": "parquet",
    ".pq": "parquet",
    ".json": "json",
    ".jsonl": "json",
    ".ndjson": "json",
}

# Magic bytes for binary format detection
_MAGIC = {
    b"PK\x03\x04": "excel",  # XLSX (ZIP archive)
    b"\xd0\xcf\x11\xe0": "excel",  # XLS (CFBF)
    b"PAR1": "parquet",
    b"\xff\xfePAR1": "parquet",
}


class FileFormatInfo:
    """Result of format detection."""

    def __init__(
        self,
        format: str,
        encoding: str = "utf-8",
        delimiter: str = ",",
        has_header: bool = True,
        is_newline_json: bool = False,
    ) -> None:
        self.format = format
        self.encoding = encoding
        self.delimiter = delimiter
        self.has_header = has_header
        self.is_newline_json = is_newline_json

    def __repr__(self) -> str:
        return (
            f"FileFormatInfo(format={self.format!r}, encoding={self.encoding!r}, "
            f"delimiter={self.delimiter!r})"
        )


class FormatDetector:
    """Detects file format and encoding from a filename and optional raw bytes."""

    def detect(
        self,
        filename: str,
        sample_bytes: bytes | None = None,
    ) -> FileFormatInfo:
        """Determine the file format, encoding, and CSV parameters.

        Args:
            filename:     Original filename (used for extension lookup).
            sample_bytes: First 4–8 KB of the file (optional; improves accuracy).

        Returns:
            ``FileFormatInfo`` with format and parameters.
        """
        ext = os.path.splitext(filename.lower())[1]

        # Extension lookup
        fmt = EXTENSION_FORMAT_MAP.get(ext)

        # Magic byte override for binary formats
        if sample_bytes and len(sample_bytes) >= 4:
            for magic, magic_fmt in _MAGIC.items():
                if sample_bytes.startswith(magic):
                    fmt = magic_fmt
                    break

        if fmt is None:
            fmt = "csv"  # safe fallback

        info = FileFormatInfo(format=fmt)

        if fmt == "csv" and sample_bytes:
            self._sniff_csv(sample_bytes, info)
        if fmt == "json" and (filename.endswith(".jsonl") or filename.endswith(".ndjson")):
            info.is_newline_json = True

        logger.debug(
            "format_detected",
            filename=filename,
            format=fmt,
            encoding=info.encoding,
            delimiter=repr(info.delimiter),
        )
        return info

    # ── CSV sniffing ──────────────────────────────────────────────────────

    def _sniff_csv(self, sample: bytes, info: FileFormatInfo) -> None:
        """Use csv.Sniffer + chardet to fill in encoding and delimiter."""
        # Encoding detection
        try:
            import chardet

            result = chardet.detect(sample)
            info.encoding = result.get("encoding") or "utf-8"
        except ImportError:
            info.encoding = self._guess_encoding(sample)

        # Delimiter sniffing
        try:
            text = sample.decode(info.encoding, errors="replace")
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t;|")
            info.delimiter = dialect.delimiter
            info.has_header = csv.Sniffer().has_header(text[:4096])
        except csv.Error:
            info.delimiter = ","
            info.has_header = True

    @staticmethod
    def _guess_encoding(sample: bytes) -> str:
        """Simple BOM-based encoding guess without chardet."""
        if sample.startswith(b"\xff\xfe"):
            return "utf-16-le"
        if sample.startswith(b"\xfe\xff"):
            return "utf-16-be"
        if sample.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig"
        return "utf-8"
