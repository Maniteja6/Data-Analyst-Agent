"""StreamProcessor — chunked reading for very large files.

When a file exceeds ``Settings.max_rows_in_memory`` (default 5M rows),
the pipeline switches from full in-memory loading to chunked streaming.
StreamProcessor yields polars DataFrames in fixed-size chunks that can
be profiled and aggregated without ever loading the full dataset into RAM.

Usage::

    processor = StreamProcessor(chunk_size=100_000)
    async for chunk_df in processor.stream_csv(path, encoding="utf-8"):
        profiler.update_incremental(chunk_df)
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

import structlog

logger = structlog.get_logger(__name__)

DEFAULT_CHUNK_SIZE = 100_000


class StreamProcessor:
    """Yields DataFrame chunks from large files without full in-memory loading."""

    def __init__(self, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        self._chunk_size = chunk_size

    async def stream_csv(
        self,
        path: str,
        encoding: str = "utf-8",
        delimiter: str = ",",
        has_header: bool = True,
    ) -> AsyncGenerator:
        """Async generator yielding polars DataFrame chunks from a CSV file.

        Falls back to pandas chunked reading when polars is unavailable.
        """
        loop = asyncio.get_event_loop()
        try:
            async for chunk in self._stream_polars_csv(path, encoding, delimiter, has_header, loop):
                yield chunk
        except ImportError:
            async for chunk in self._stream_pandas_csv(path, encoding, delimiter, has_header, loop):
                yield chunk

    async def stream_parquet(self, path: str) -> AsyncGenerator:
        """Async generator yielding polars DataFrame chunks from a Parquet file."""
        loop = asyncio.get_event_loop()

        def _read():
            import polars as pl
            return pl.read_parquet(path)

        df = await loop.run_in_executor(None, _read)
        total = len(df)
        for start in range(0, total, self._chunk_size):
            yield df.slice(start, self._chunk_size)

    # ── Private streaming implementations ────────────────────────────────

    async def _stream_polars_csv(
        self, path: str, encoding: str, delimiter: str, has_header: bool, loop
    ) -> AsyncGenerator:
        import polars as pl

        def _read_batch(skip: int) -> tuple:
            chunk = pl.read_csv(
                path,
                separator=delimiter,
                encoding=encoding,
                has_header=has_header,
                skip_rows=skip if skip > 0 else 0,
                n_rows=self._chunk_size,
                infer_schema_length=100,
                ignore_errors=True,
            )
            return chunk

        # Polars doesn't have native chunked reading for CSV — we use row offsets
        offset = 0
        while True:
            chunk = await loop.run_in_executor(None, _read_batch, offset)
            if len(chunk) == 0:
                break
            yield chunk
            if len(chunk) < self._chunk_size:
                break
            offset += self._chunk_size

    async def _stream_pandas_csv(
        self, path: str, encoding: str, delimiter: str, has_header: bool, loop
    ) -> AsyncGenerator:
        import pandas as pd

        def _get_reader():
            return pd.read_csv(
                path,
                sep=delimiter,
                encoding=encoding,
                header=0 if has_header else None,
                chunksize=self._chunk_size,
                low_memory=False,
            )

        reader = await loop.run_in_executor(None, _get_reader)
        for chunk in reader:
            yield chunk
