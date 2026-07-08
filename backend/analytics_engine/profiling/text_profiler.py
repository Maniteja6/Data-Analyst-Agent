"""TextProfiler — length statistics and pattern analysis for free-text columns."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    import pandas as pd
    import polars as pl

    DataFrameT = pl.DataFrame | pd.DataFrame

logger = structlog.get_logger(__name__)


class TextProfiler:
    """Profiles text/string columns for length distribution and patterns."""

    def profile(self, df: DataFrameT, column: str) -> dict:
        """Return a dict of text statistics."""
        try:
            return self._profile_polars(df, column)
        except Exception:
            return self._profile_pandas(df, column)

    def _profile_polars(self, df: DataFrameT, column: str) -> dict:
        import polars as pl

        series = df[column].drop_nulls().cast(pl.Utf8)
        n = len(series)
        if n == 0:
            return {}

        lengths = series.str.len_chars()
        return {
            "non_null_count": n,
            "min_length": int(lengths.min()),
            "max_length": int(lengths.max()),
            "avg_length": round(float(lengths.mean()), 2),
            "has_whitespace": bool(series.str.contains(r"^\s|\s$").any()),
            "sample_values": series.head(5).to_list(),
        }

    def _profile_pandas(self, df: DataFrameT, column: str) -> dict:
        series = df[column].dropna().astype(str)
        n = len(series)
        if n == 0:
            return {}
        lengths = series.str.len()
        return {
            "non_null_count": n,
            "min_length": int(lengths.min()),
            "max_length": int(lengths.max()),
            "avg_length": round(float(lengths.mean()), 2),
            "has_whitespace": bool(
                series.str.startswith(" ").any() or series.str.endswith(" ").any()
            ),
            "sample_values": series.head(5).tolist(),
        }
