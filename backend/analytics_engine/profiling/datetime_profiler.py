"""DatetimProfiler — range, granularity, and gap analysis for datetime columns."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from typing import TypeAlias

    import pandas as pd
    import polars as pl

    DataFrameT: TypeAlias = pl.DataFrame | pd.DataFrame

logger = structlog.get_logger(__name__)


class DatetimeProfiler:
    """Profiles datetime columns for range, gaps, and series regularity."""

    def profile(self, df: DataFrameT, column: str) -> dict:
        """Return a dict of datetime statistics for the given column."""
        try:
            return self._profile_polars(df, column)
        except Exception:
            return self._profile_pandas(df, column)

    def _profile_polars(self, df: DataFrameT, column: str) -> dict:
        series = df[column].drop_nulls().sort()
        n = len(series)
        if n == 0:
            return {}

        min_dt = series[0]
        max_dt = series[-1]

        # Detect inferred frequency (daily, weekly, monthly, etc.)
        if n > 2:
            diffs = series.diff().drop_nulls()
            median_d = diffs.median()
        else:
            median_d = None

        return {
            "min_date": str(min_dt),
            "max_date": str(max_dt),
            "date_range_days": (max_dt - min_dt).days
            if hasattr((max_dt - min_dt), "days")
            else None,
            "non_null_count": n,
            "unique_dates": series.n_unique(),
            "inferred_frequency": self._infer_frequency(median_d),
            "has_gaps": self._has_gaps(series, median_d),
        }

    def _profile_pandas(self, df: DataFrameT, column: str) -> dict:
        import pandas as pd

        series = pd.to_datetime(df[column], errors="coerce").dropna().sort_values()
        n = len(series)
        if n == 0:
            return {}
        diffs = series.diff().dropna()
        median_d = diffs.median().total_seconds() / 86400 if len(diffs) > 0 else None
        return {
            "min_date": str(series.min()),
            "max_date": str(series.max()),
            "date_range_days": (series.max() - series.min()).days,
            "non_null_count": n,
            "unique_dates": series.nunique(),
            "inferred_frequency": self._infer_frequency(median_d),
            "has_gaps": False,
        }

    @staticmethod
    def _infer_frequency(median_days: Any) -> str:  # noqa: ANN401 — float or pandas Timedelta
        if median_days is None:
            return "unknown"
        d = float(median_days) if not hasattr(median_days, "days") else median_days.days
        if d <= 1.5:
            return "daily"
        if d <= 8:
            return "weekly"
        if d <= 16:
            return "bi-weekly"
        if d <= 35:
            return "monthly"
        if d <= 100:
            return "quarterly"
        return "annual_or_irregular"

    @staticmethod
    def _has_gaps(series: Any, median_d: Any) -> bool:  # noqa: ANN401 — polars or pandas Series
        """True if any gap is more than 2× the median interval."""
        if median_d is None or len(series) < 3:
            return False
        try:
            diffs = series.diff().drop_nulls()
            return any(abs(float(d)) > abs(float(median_d)) * 2 for d in diffs)
        except Exception:
            return False
