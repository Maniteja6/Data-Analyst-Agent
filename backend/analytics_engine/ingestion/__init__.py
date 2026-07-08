"""Ingestion — async file loading with format auto-detection.

FileReader:      async read(storage_key, sample_rows) → polars/pandas DataFrame.
                 Dispatches to polars (preferred) or pandas by format.
FormatDetector:  magic-byte + extension + csv.Sniffer → FileFormatInfo.
StreamProcessor: async generator for files exceeding max_rows_in_memory.
"""

from backend.analytics_engine.ingestion.file_reader import FileReader
from backend.analytics_engine.ingestion.format_detector import FormatDetector

__all__ = ["FileReader", "FormatDetector"]
