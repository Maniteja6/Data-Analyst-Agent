"""CategoricalProfiler — frequency analysis for categorical / text columns."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from backend.domain.analytics.value_objects.histogram import Histogram

if TYPE_CHECKING:
    from typing import TypeAlias

    import pandas as pd
    import polars as pl

    DataFrameT: TypeAlias = pl.DataFrame | pd.DataFrame

logger = structlog.get_logger(__name__)


class CategoricalProfiler:
    """Computes top-N value frequencies and a categorical Histogram."""

    def __init__(self, top_n: int = 20) -> None:
        self._top_n = top_n

    def profile(self, df: DataFrameT, column: str) -> tuple[list[dict], Histogram | None]:
        """Return (top_values list, Histogram) for the given column."""
        try:
            return self._profile_polars(df, column)
        except Exception:
            return self._profile_pandas(df, column)

    def _profile_polars(self, df: DataFrameT, column: str) -> tuple[list[dict], Histogram | None]:
        series = df[column].drop_nulls()
        n = len(series)
        if n == 0:
            return [], None

        counts = series.value_counts().sort("count", descending=True).head(self._top_n)

        top_values = [
            {
                "value": str(row[column]),
                "count": int(row["count"]),
                "pct": round(int(row["count"]) / n, 6),
            }
            for row in counts.iter_rows(named=True)
        ]

        value_count_dict = {row[column]: row["count"] for row in counts.iter_rows(named=True)}
        histogram = Histogram.from_value_counts(
            column_name=column,
            counts=value_count_dict,
            top_n=self._top_n,
        )
        return top_values, histogram

    def _profile_pandas(self, df: DataFrameT, column: str) -> tuple[list[dict], Histogram | None]:
        series = df[column].dropna()
        n = len(series)
        if n == 0:
            return [], None

        vc = series.value_counts().head(self._top_n)
        top_values = [
            {"value": str(k), "count": int(v), "pct": round(v / n, 6)} for k, v in vc.items()
        ]
        histogram = Histogram.from_value_counts(
            column_name=column,
            counts={k: int(v) for k, v in vc.items()},
            top_n=self._top_n,
        )
        return top_values, histogram
