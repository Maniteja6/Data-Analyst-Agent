"""Z-score anomaly detector — flags values that deviate from the column median.

Uses the "modified Z-score" (Iglewicz & Hoaglin): median and MAD (median
absolute deviation) in place of mean and standard deviation. A classical
mean/std Z-score is vulnerable to exactly the values it's trying to
detect — one extreme outlier inflates the mean and std enough to mask
its own Z-score (e.g. a single 999 among values around 10-12 can pull
its own Z-score under a threshold of 3, since the outlier itself
dominates the standard deviation it's being measured against). Median
and MAD are robust order statistics that a single extreme value can't
meaningfully distort.

    modified_z = 0.6745 * (x - median) / MAD

The 0.6745 constant makes the modified Z-score comparable in scale to a
classical Z-score under normality (0.6745 ≈ the 0.75 quantile of the
standard normal distribution).

Strengths:
  - Robust to the outlier it's detecting — one extreme value doesn't
    mask itself the way it would with mean/std
  - Interpretable: same threshold semantics as a classical Z-score
  - Low false-positive rate for normally distributed data

Weaknesses:
  - Assumes approximate unimodality; less meaningful for multimodal data
  - Not appropriate for categorical or boolean columns

When to prefer over IQR:
  - Data is roughly bell-shaped (skewness |s| < 1)
  - You need a probability interpretation (Z → p-value)

Usage::

    detector = ZScoreDetector(threshold=3.0)
    results  = detector.detect(df, column="revenue")
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
class ZScoreAnomaly:
    """One outlier flagged by the Z-score detector."""

    column_name: str
    row_index: int
    raw_value: float
    z_score: float
    confidence: float  # |z| / (|z| + threshold) — 0.5 at boundary, 1.0 at ∞


class ZScoreDetector:
    """Detects numeric outliers using the Z-score method.

    Args:
        threshold:      Minimum |Z| to flag a value. Default: 3.0 (99.7% CI).
        max_results:    Cap on anomalies per column (avoids flooding for pathological data).
    """

    def __init__(self, threshold: float = 3.0, max_results: int = 100) -> None:
        self._threshold = threshold
        self._max_results = max_results

    def detect(self, df: DataFrameT, column: str) -> list[ZScoreAnomaly]:
        """Run Z-score detection on one numeric column.

        Args:
            df:     A polars or pandas DataFrame.
            column: Column name to analyse. Must be numeric.

        Returns:
            List of ``ZScoreAnomaly`` objects for flagged rows, sorted by |Z| descending.
        """
        try:
            return self._detect_polars(df, column)
        except Exception:
            return self._detect_pandas(df, column)

    def _detect_polars(self, df: DataFrameT, column: str) -> list[ZScoreAnomaly]:
        series = df[column].drop_nulls()
        if series.len() < 10:
            return []

        median = series.median()
        if median is None:
            return []
        mad = (series - median).abs().median()
        if mad is None or mad == 0:
            return []

        # Compute modified Z-scores for the full (non-null) column
        col_data = df[column].to_list()
        results = []
        for idx, val in enumerate(col_data):
            if val is None:
                continue
            z = 0.6745 * (val - median) / mad
            if abs(z) >= self._threshold:
                confidence = abs(z) / (abs(z) + self._threshold)
                results.append(
                    ZScoreAnomaly(
                        column_name=column,
                        row_index=idx,
                        raw_value=float(val),
                        z_score=round(z, 4),
                        confidence=round(confidence, 4),
                    )
                )
            if len(results) >= self._max_results:
                break

        results.sort(key=lambda x: abs(x.z_score), reverse=True)
        logger.debug(
            "zscore_detection_complete",
            column=column,
            anomaly_count=len(results),
            threshold=self._threshold,
        )
        return results

    def _detect_pandas(self, df: DataFrameT, column: str) -> list[ZScoreAnomaly]:
        series = df[column].dropna()
        if len(series) < 10:
            return []

        median = series.median()
        mad = (series - median).abs().median()
        if mad == 0:
            return []

        z_scores = (0.6745 * (df[column] - median) / mad).abs()
        mask = z_scores >= self._threshold
        flagged = df[mask].head(self._max_results)
        results = []
        for idx, row in flagged.iterrows():
            z = 0.6745 * (row[column] - median) / mad
            confidence = abs(z) / (abs(z) + self._threshold)
            results.append(
                ZScoreAnomaly(
                    column_name=column,
                    row_index=int(idx),
                    raw_value=float(row[column]),
                    z_score=round(z, 4),
                    confidence=round(confidence, 4),
                )
            )

        results.sort(key=lambda x: abs(x.z_score), reverse=True)
        return results

    def to_anomaly_dicts(self, column: str, df: DataFrameT) -> list[dict]:
        """Run detection and return results as plain dicts for the pipeline."""
        anomalies = self.detect(df, column)
        return [
            {
                "column": a.column_name,
                "detection_method": "ZScore",
                "anomaly_type": "outlier",
                "severity": "high" if abs(a.z_score) > 5 else "medium",
                "confidence": a.confidence,
                "rows_affected": 1,
                "value": str(a.raw_value),
                "row_index": a.row_index,
                "description": (
                    f"Value {a.raw_value:.4g} in '{column}' has Z-score {a.z_score:.2f} "
                    f"({abs(a.z_score):.1f}σ from the mean)."
                ),
            }
            for a in anomalies
        ]
