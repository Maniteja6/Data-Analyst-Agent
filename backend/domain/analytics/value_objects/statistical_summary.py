"""StatisticalSummary value object — descriptive statistics for a numeric column."""

from __future__ import annotations

from dataclasses import dataclass

from backend.shared.value_object import ValueObject


@dataclass(frozen=True)
class StatisticalSummary(ValueObject):
    """Immutable snapshot of key descriptive statistics for one numeric column.

    All float fields are ``None`` when they cannot be computed
    (e.g. a column with all-null values, or a non-numeric column).

    Used inside ``ColumnProfile`` to keep the profile entity lean while
    allowing the full stats to be serialised to JSON for the insight agents.
    """

    count: int  # total non-null observations
    mean: float | None = None
    stddev: float | None = None
    variance: float | None = None
    min_val: float | None = None
    max_val: float | None = None
    p05: float | None = None  # 5th  percentile
    p25: float | None = None  # 25th percentile (Q1)
    p50: float | None = None  # 50th percentile (median)
    p75: float | None = None  # 75th percentile (Q3)
    p95: float | None = None  # 95th percentile
    skewness: float | None = None  # Pearson's skewness
    kurtosis: float | None = None  # excess kurtosis (Fisher definition)

    def _validate(self) -> None:
        if self.count < 0:
            raise ValueError(f"count must be non-negative, got {self.count}")

    @property
    def iqr(self) -> float | None:
        """Interquartile range (Q3 - Q1). Returns None if quartiles are missing."""
        if self.p25 is not None and self.p75 is not None:
            return round(self.p75 - self.p25, 6)
        return None

    @property
    def range(self) -> float | None:
        """Max - Min. Returns None if either bound is missing."""
        if self.min_val is not None and self.max_val is not None:
            return round(self.max_val - self.min_val, 6)
        return None

    @property
    def cv(self) -> float | None:
        """Coefficient of variation (stddev / mean). Returns None when mean is 0."""
        if self.stddev is not None and self.mean:
            return round(abs(self.stddev / self.mean), 6)
        return None

    @property
    def is_right_skewed(self) -> bool | None:
        """True when skewness > 0.5 (moderately right-skewed)."""
        if self.skewness is None:
            return None
        return self.skewness > 0.5

    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "mean": self.mean,
            "stddev": self.stddev,
            "min": self.min_val,
            "max": self.max_val,
            "p25": self.p25,
            "p50": self.p50,
            "p75": self.p75,
            "iqr": self.iqr,
            "skewness": self.skewness,
            "kurtosis": self.kurtosis,
        }
