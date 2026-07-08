"""StatisticsCalculator — supplementary per-column statistics for the profiling agent.

Computes metrics not included in DataProfiler by default:
    - Coefficient of variation (relative variability)
    - Shannon entropy (categorical distribution spread)
    - Gini coefficient (inequality measure for revenue/count columns)
    - Interquartile range (IQR — used by anomaly detection)
    - Outlier count (IQR-based, for the profiling summary card)

Real-time design:
    All methods are pure computation — no I/O, no LLM calls.
    Called synchronously from the profiling thread so results are ready
    before the ``profiling:column_complete`` Socket.IO event fires.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from typing import TypeAlias

    import pandas as pd
    import polars as pl

    SeriesT: TypeAlias = pl.Series | pd.Series


class StatisticsCalculator:
    """Supplementary statistics for numeric and categorical columns."""

    # ── Numeric ───────────────────────────────────────────────────────────

    @staticmethod
    def coefficient_of_variation(mean: float, stddev: float) -> float | None:
        """CV = stddev / |mean| — measures relative variability.

        High CV (> 1.0) signals high spread relative to the average.
        Returns None when mean is zero (undefined).
        """
        if mean == 0:
            return None
        return round(abs(stddev / mean), 6)

    @staticmethod
    def interquartile_range(p25: float, p75: float) -> float:
        """IQR = P75 - P25 — used for Tukey fence anomaly detection."""
        return round(p75 - p25, 6)

    @staticmethod
    def tukey_fences(
        p25: float,
        p75: float,
        multiplier: float = 1.5,
    ) -> tuple[float, float]:
        """Return (lower_fence, upper_fence) for Tukey outlier detection."""
        iqr = p75 - p25
        lower = p25 - multiplier * iqr
        upper = p75 + multiplier * iqr
        return round(lower, 6), round(upper, 6)

    @staticmethod
    def outlier_count(
        series: SeriesT,
        p25: float,
        p75: float,
        multiplier: float = 1.5,
    ) -> int:
        """Count values outside the Tukey fences.

        Args:
            series:     Polars or pandas Series (numeric).
            p25, p75:   Quantile values.
            multiplier: Fence multiplier (1.5 = mild, 3.0 = extreme).
        """
        lower, upper = StatisticsCalculator.tukey_fences(p25, p75, multiplier)
        try:
            # polars
            return int(((series < lower) | (series > upper)).drop_nulls().sum())
        except Exception:
            try:
                # pandas
                mask = (series < lower) | (series > upper)
                return int(mask.sum())
            except Exception:
                return 0

    @staticmethod
    def gini_coefficient(values: list[float]) -> float:
        """Compute the Gini coefficient (0 = perfect equality, 1 = max inequality).

        Useful for revenue columns to measure distribution inequality.
        Reference: https://en.wikipedia.org/wiki/Gini_coefficient
        """
        if not values or len(values) < 2:
            return 0.0
        non_neg = sorted(abs(v) for v in values if v is not None)
        n = len(non_neg)
        if n == 0 or sum(non_neg) == 0:
            return 0.0
        cumsum = 0.0
        for i, v in enumerate(non_neg):
            cumsum += (2 * (i + 1) - n - 1) * v
        return round(cumsum / (n * sum(non_neg)), 6)

    # ── Categorical ───────────────────────────────────────────────────────

    @staticmethod
    def shannon_entropy(value_counts: dict[str, int]) -> float:
        """Shannon entropy of a categorical distribution (bits).

        High entropy → many equally-distributed categories (high diversity).
        Low entropy → dominated by one or two categories.

        Returns 0.0 for empty distributions.
        """
        total = sum(value_counts.values())
        if total == 0:
            return 0.0
        probs = [c / total for c in value_counts.values() if c > 0]
        return round(-sum(p * math.log2(p) for p in probs), 6)

    @staticmethod
    def normalised_entropy(value_counts: dict[str, int]) -> float:
        """Entropy normalised to [0, 1] by log2(n_categories).

        Easier to interpret than raw entropy because it's independent of
        the number of categories.
        """
        n = len(value_counts)
        if n <= 1:
            return 0.0
        raw = StatisticsCalculator.shannon_entropy(value_counts)
        return round(raw / math.log2(n), 6)

    @staticmethod
    def top_k_coverage(value_counts: dict[str, int], k: int = 3) -> float:
        """Fraction of rows covered by the top-k most frequent values.

        A high top-3 coverage (> 0.8) indicates the column is dominated
        by a few values — often a sign of a useful grouping variable.
        """
        if not value_counts:
            return 0.0
        total = sum(value_counts.values())
        top_k = sorted(value_counts.values(), reverse=True)[:k]
        return round(sum(top_k) / max(total, 1), 6)

    # ── Summary builder ───────────────────────────────────────────────────

    @classmethod
    def compute_supplementary(
        cls,
        kind: str,
        stats: dict | None = None,
        value_counts: dict[str, int] | None = None,
        series: SeriesT | None = None,
    ) -> dict[str, Any]:
        """Compute all applicable supplementary statistics for one column.

        Args:
            kind:         'numeric' | 'text' | 'boolean' | other
            stats:        StatisticalSummary.to_dict() (numeric columns)
            value_counts: {value: count} dict (categorical columns)
            series:       Raw polars/pandas Series (for outlier count)

        Returns:
            Dict of supplementary statistics keyed by metric name.
        """
        result: dict[str, Any] = {}

        if kind == "numeric" and stats:
            mean = stats.get("mean", 0) or 0
            stddev = stats.get("stddev", 0) or 0
            p25 = stats.get("p25") or 0
            p75 = stats.get("p75") or 0

            result["cv"] = cls.coefficient_of_variation(mean, stddev)
            result["iqr"] = cls.interquartile_range(p25, p75)
            result["tukey_lower"], result["tukey_upper"] = cls.tukey_fences(p25, p75)

            if series is not None:
                result["outlier_count_iqr"] = cls.outlier_count(series, p25, p75)

        if value_counts:
            result["entropy"] = cls.shannon_entropy(value_counts)
            result["normalised_entropy"] = cls.normalised_entropy(value_counts)
            result["top3_coverage"] = cls.top_k_coverage(value_counts, k=3)

        return result
