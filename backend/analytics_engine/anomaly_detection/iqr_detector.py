"""IQR (Interquartile Range) anomaly detector — Tukey fence method.

The Tukey fence method defines outlier bounds as:
    lower = Q1 - multiplier * IQR
    upper = Q3 + multiplier * IQR

where IQR = Q3 - Q1 and multiplier = 1.5 (mild outlier) or 3.0 (extreme).

Strengths:
  - Robust to the outliers it is detecting (uses order statistics, not mean/std)
  - Works well on skewed distributions
  - No normality assumption

Weaknesses:
  - Misses outliers in highly clustered data (tight Q1–Q3 → very tight fences)
  - Fixed multiplicative fences don't adapt to distribution shape
  - Not appropriate for categorical or datetime columns

When to prefer over Z-score:
  - Data is skewed (skewness |s| > 1)
  - Outliers are suspected to distort the mean
  - Domain knowledge suggests Tukey fences are industry-standard (e.g. box plots)

Usage::

    detector = IQRDetector(multiplier=1.5)
    results  = detector.detect(df, column="price")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import TypeAlias

    import pandas as pd
    import polars as pl

    DataFrameT: TypeAlias = pl.DataFrame | pd.DataFrame

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class IQRAnomaly:
    """One outlier flagged by the IQR detector."""

    column_name: str
    row_index: int
    raw_value: float
    lower_fence: float
    upper_fence: float
    direction: str  # "above_upper" | "below_lower"
    distance: float  # signed distance from the violated fence


class IQRDetector:
    """Detects numeric outliers using Tukey's fence (IQR method).

    Args:
        multiplier:  Fence multiplier. 1.5 = mild outlier, 3.0 = extreme.
        max_results: Cap on anomalies per column.
    """

    # Unlike Z-score (which needs a reasonably large sample for mean/std to
    # be meaningful), Tukey fences only need enough points to interpolate
    # Q1 and Q3 — 4 is the practical minimum for a non-degenerate quartile split.
    MIN_SAMPLES = 4

    def __init__(self, multiplier: float = 1.5, max_results: int = 100) -> None:
        self._multiplier = multiplier
        self._max_results = max_results

    def detect(self, df: DataFrameT, column: str) -> list[IQRAnomaly]:
        """Run IQR detection on one numeric column."""
        try:
            return self._detect_polars(df, column)
        except Exception:
            return self._detect_pandas(df, column)

    def _detect_polars(self, df: DataFrameT, column: str) -> list[IQRAnomaly]:
        series = df[column].drop_nulls()
        if series.len() < self.MIN_SAMPLES:
            return []

        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            return []

        lower = q1 - self._multiplier * iqr
        upper = q3 + self._multiplier * iqr

        col_data = df[column].to_list()
        results = []
        for idx, val in enumerate(col_data):
            if val is None:
                continue
            if val < lower or val > upper:
                direction = "above_upper" if val > upper else "below_lower"
                fence = upper if val > upper else lower
                results.append(
                    IQRAnomaly(
                        column_name=column,
                        row_index=idx,
                        raw_value=float(val),
                        lower_fence=round(lower, 6),
                        upper_fence=round(upper, 6),
                        direction=direction,
                        distance=round(val - fence, 6),
                    )
                )
            if len(results) >= self._max_results:
                break

        results.sort(key=lambda x: abs(x.distance), reverse=True)
        logger.debug(
            "iqr_detection_complete",
            column=column,
            lower=lower,
            upper=upper,
            anomaly_count=len(results),
        )
        return results

    def _detect_pandas(self, df: DataFrameT, column: str) -> list[IQRAnomaly]:
        series = df[column].dropna()
        if len(series) < self.MIN_SAMPLES:
            return []

        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            return []

        lower = q1 - self._multiplier * iqr
        upper = q3 + self._multiplier * iqr

        mask = (df[column] < lower) | (df[column] > upper)
        flagged = df[mask].head(self._max_results)
        results = []
        for idx, row in flagged.iterrows():
            val = row[column]
            direction = "above_upper" if val > upper else "below_lower"
            fence = upper if val > upper else lower
            results.append(
                IQRAnomaly(
                    column_name=column,
                    row_index=int(idx),
                    raw_value=float(val),
                    lower_fence=round(float(lower), 6),
                    upper_fence=round(float(upper), 6),
                    direction=direction,
                    distance=round(float(val - fence), 6),
                )
            )

        results.sort(key=lambda x: abs(x.distance), reverse=True)
        return results

    def to_anomaly_dicts(self, column: str, df: DataFrameT) -> list[dict]:
        """Run detection and return plain dicts for the pipeline."""
        anomalies = self.detect(df, column)
        return [
            {
                "column": a.column_name,
                "detection_method": "IQR",
                "anomaly_type": "outlier",
                "severity": "low",
                "confidence": 0.70,
                "rows_affected": 1,
                "value": str(a.raw_value),
                "row_index": a.row_index,
                "description": (
                    f"Value {a.raw_value:.4g} in '{column}' is "
                    f"{'above the upper' if a.direction == 'above_upper' else 'below the lower'} "
                    f"IQR fence ({a.upper_fence:.4g} / {a.lower_fence:.4g})."
                ),
            }
            for a in anomalies
        ]
