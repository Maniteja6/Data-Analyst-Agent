"""FileReader — reads uploaded dataset files into polars DataFrames.

Supports CSV/TSV, Excel (XLSX/XLS), Parquet, and JSON/JSONL.
Automatically detects format via FormatDetector and applies encoding
and delimiter settings without caller involvement.

For files smaller than ``Settings.max_rows_in_memory``, the full DataFrame
is returned. For larger files, callers should use ``StreamProcessor`` instead.

Usage::

    reader = FileReader()
    df     = await reader.read("datasets/abc-123/sales.csv")
    # or with an explicit local path:
    df     = await reader.read_path("/tmp/datapilot_storage/datasets/abc/sales.csv")
"""
from __future__ import annotations

import asyncio
import io
import os

import structlog

from backend.analytics_engine.ingestion.format_detector import FormatDetector, FileFormatInfo
from backend.config.settings import get_settings

logger = structlog.get_logger(__name__)


class FileReader:
    """Async file reader that returns a polars (or pandas) DataFrame."""

    def __init__(self, storage_adapter=None) -> None:
        self._storage  = storage_adapter
        self._detector = FormatDetector()

    async def read(
        self,
        storage_key: str,
        sample_rows: int | None = None,
    ):
        """Read a dataset file from S3/MinIO and return a DataFrame.

        Args:
            storage_key: S3/MinIO object key (e.g. ``'datasets/abc-123/sales.csv'``).
            sample_rows: If set, read only this many rows (useful for quick schema inference).

        Returns:
            polars or pandas DataFrame.
        """
        storage = self._get_storage()
        raw     = await storage.download_bytes(storage_key)
        filename = os.path.basename(storage_key)
        fmt_info = self._detector.detect(filename, sample_bytes=raw[:8192])

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._parse(raw, fmt_info, filename, sample_rows),
        )

    async def read_path(
        self,
        local_path: str,
        sample_rows: int | None = None,
    ):
        """Read a dataset file from the local filesystem.

        Used by the local storage adapter and in tests.
        """
        with open(local_path, "rb") as f:
            raw = f.read()
        filename = os.path.basename(local_path)
        fmt_info = self._detector.detect(filename, sample_bytes=raw[:8192])

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._parse(raw, fmt_info, filename, sample_rows),
        )

    # ── Parse dispatch ────────────────────────────────────────────────────

    def _parse(self, raw: bytes, info: FileFormatInfo, filename: str, sample_rows: int | None):
        if info.format == "csv":
            return self._parse_csv(raw, info, sample_rows)
        if info.format == "excel":
            return self._parse_excel(raw, filename, sample_rows)
        if info.format == "parquet":
            return self._parse_parquet(raw, sample_rows)
        if info.format == "json":
            return self._parse_json(raw, info, sample_rows)
        raise ValueError(f"Unsupported file format: {info.format!r}")

    # ── Format parsers ────────────────────────────────────────────────────

    def _parse_csv(self, raw: bytes, info: FileFormatInfo, sample_rows: int | None):
        try:
            import polars as pl
            kwargs = {
                "separator":           info.delimiter,
                "encoding":            info.encoding if info.encoding != "utf-8-sig" else "utf8",
                "has_header":          info.has_header,
                "infer_schema_length": 500,
                "ignore_errors":       True,
                "null_values":         ["", "NA", "N/A", "null", "NULL", "None", "#N/A", "NaN"],
            }
            if sample_rows:
                kwargs["n_rows"] = sample_rows

            df = pl.read_csv(io.BytesIO(raw), **kwargs)
            logger.info("csv_read_polars", rows=len(df), cols=len(df.columns))
            return df

        except Exception as exc:
            logger.warning("polars_csv_failed_fallback_pandas", error=str(exc))
            return self._parse_csv_pandas(raw, info, sample_rows)

    def _parse_csv_pandas(self, raw: bytes, info: FileFormatInfo, sample_rows: int | None):
        import pandas as pd
        kwargs = {
            "sep":       info.delimiter,
            "encoding":  info.encoding,
            "header":    0 if info.has_header else None,
            "na_values": ["", "NA", "N/A", "null", "NULL", "None", "#N/A"],
            "low_memory": False,
        }
        if sample_rows:
            kwargs["nrows"] = sample_rows
        return pd.read_csv(io.BytesIO(raw), **kwargs)

    def _parse_excel(self, raw: bytes, filename: str, sample_rows: int | None):
        try:
            import polars as pl
            kwargs = {}
            if sample_rows:
                kwargs["n_rows"] = sample_rows
            df = pl.read_excel(io.BytesIO(raw), read_options=kwargs)
            logger.info("excel_read_polars", rows=len(df), cols=len(df.columns))
            return df
        except Exception as exc:
            logger.warning("polars_excel_failed_fallback_pandas", error=str(exc))
            import pandas as pd
            engine = "xlrd" if filename.endswith(".xls") else "openpyxl"
            kwargs = {"engine": engine}
            if sample_rows:
                kwargs["nrows"] = sample_rows
            return pd.read_excel(io.BytesIO(raw), **kwargs)

    def _parse_parquet(self, raw: bytes, sample_rows: int | None):
        try:
            import polars as pl
            df = pl.read_parquet(io.BytesIO(raw), n_rows=sample_rows)
            logger.info("parquet_read_polars", rows=len(df), cols=len(df.columns))
            return df
        except Exception as exc:
            logger.warning("polars_parquet_failed_fallback_pandas", error=str(exc))
            import pandas as pd
            df = pd.read_parquet(io.BytesIO(raw))
            return df.head(sample_rows) if sample_rows else df

    def _parse_json(self, raw: bytes, info: FileFormatInfo, sample_rows: int | None):
        try:
            import polars as pl
            if info.is_newline_json:
                df = pl.read_ndjson(io.BytesIO(raw), n_rows=sample_rows)
            else:
                df = pl.read_json(io.BytesIO(raw))
                if sample_rows:
                    df = df.head(sample_rows)
            return df
        except Exception as exc:
            logger.warning("polars_json_failed_fallback_pandas", error=str(exc))
            import pandas as pd
            if info.is_newline_json:
                df = pd.read_json(io.BytesIO(raw), lines=True)
            else:
                df = pd.read_json(io.BytesIO(raw))
            return df.head(sample_rows) if sample_rows else df

    def _get_storage(self):
        if self._storage is None:
            from backend.infrastructure.storage.s3_storage_adapter import get_s3_storage
            self._storage = get_s3_storage()
        return self._storage
