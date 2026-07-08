"""NumericProfiler — descriptive statistics for numeric columns."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from backend.domain.analytics.value_objects.histogram import Histogram
from backend.domain.analytics.value_objects.statistical_summary import StatisticalSummary

if TYPE_CHECKING:
    from typing import TypeAlias

    import pandas as pd
    import polars as pl

    DataFrameT: TypeAlias = pl.DataFrame | pd.DataFrame

logger = structlog.get_logger(__name__)


class NumericProfiler:
    """Computes StatisticalSummary and Histogram for a numeric column."""

    def __init__(self, histogram_bins: int = 20, sample_size: int = 100_000) -> None:
        self._bins = histogram_bins
        self._sample_size = sample_size

    def profile(
        self, df: DataFrameT, column: str
    ) -> tuple[StatisticalSummary | None, Histogram | None]:
        """Return (StatisticalSummary, Histogram) for the given column."""
        try:
            return self._profile_polars(df, column)
        except Exception:
            return self._profile_pandas(df, column)

    def _profile_polars(
        self, df: DataFrameT, column: str
    ) -> tuple[StatisticalSummary | None, Histogram | None]:
        series = df[column].drop_nulls()
        n = len(series)
        if n == 0:
            return None, None

        # Sample for histograms on large datasets
        hist_series = (
            series.sample(min(n, self._sample_size), seed=42) if n > self._sample_size else series
        )

        stats = StatisticalSummary(
            count=n,
            mean=round(float(series.mean()), 6),
            stddev=round(float(series.std()), 6),
            variance=round(float(series.var()), 6),
            min_val=float(series.min()),
            max_val=float(series.max()),
            p05=round(float(series.quantile(0.05)), 6),
            p25=round(float(series.quantile(0.25)), 6),
            p50=round(float(series.quantile(0.50)), 6),
            p75=round(float(series.quantile(0.75)), 6),
            p95=round(float(series.quantile(0.95)), 6),
            skewness=round(float(series.skew()), 6) if hasattr(series, "skew") else None,
            kurtosis=round(float(series.kurtosis()), 6) if hasattr(series, "kurtosis") else None,
        )

        # Build histogram via numpy cut
        try:
            import numpy as np

            vals = hist_series.to_numpy()
            counts, edges = np.histogram(vals, bins=min(self._bins, max(5, len(set(vals)))))
            histogram = Histogram.from_numeric_ranges(
                column_name=column,
                bin_edges=edges.tolist(),
                bin_counts=counts.tolist(),
            )
        except Exception:
            histogram = None

        return stats, histogram

    def _profile_pandas(
        self, df: DataFrameT, column: str
    ) -> tuple[StatisticalSummary | None, Histogram | None]:
        import numpy as np
        from scipy import stats as scipy_stats

        series = df[column].dropna()
        n = len(series)
        if n == 0:
            return None, None

        summary = StatisticalSummary(
            count=n,
            mean=round(float(series.mean()), 6),
            stddev=round(float(series.std()), 6),
            variance=round(float(series.var()), 6),
            min_val=float(series.min()),
            max_val=float(series.max()),
            p05=round(float(np.percentile(series, 5)), 6),
            p25=round(float(np.percentile(series, 25)), 6),
            p50=round(float(np.percentile(series, 50)), 6),
            p75=round(float(np.percentile(series, 75)), 6),
            p95=round(float(np.percentile(series, 95)), 6),
            skewness=round(float(scipy_stats.skew(series)), 6),
            kurtosis=round(float(scipy_stats.kurtosis(series)), 6),
        )
        try:
            counts, edges = np.histogram(series.values, bins=self._bins)
            histogram = Histogram.from_numeric_ranges(column, edges.tolist(), counts.tolist())
        except Exception:
            histogram = None

        return summary, histogram
