"""CorrelationEngine — pairwise correlation across all numeric columns."""
from __future__ import annotations

import structlog
from backend.domain.analytics.value_objects.correlation_coefficient import (
    CorrelationCoefficient, CorrelationMethod,
)

logger = structlog.get_logger(__name__)


class CorrelationEngine:
    """Computes pairwise Pearson correlations between numeric columns."""

    def __init__(self, min_abs_r: float = 0.3, max_pairs: int = 200) -> None:
        self._min_r    = min_abs_r
        self._max_pairs = max_pairs

    def compute(self, df, numeric_columns: list[str]) -> list[CorrelationCoefficient]:
        """Return significant pairwise correlations (|r| ≥ min_abs_r)."""
        if len(numeric_columns) < 2:
            return []
        try:
            return self._compute_polars(df, numeric_columns)
        except Exception:
            return self._compute_pandas(df, numeric_columns)

    def _compute_polars(self, df, cols: list[str]) -> list[CorrelationCoefficient]:
        import polars as pl
        results = []
        for i, col_a in enumerate(cols):
            for col_b in cols[i+1:]:
                try:
                    r = df.select(pl.pearson_corr(col_a, col_b)).item()
                    if r is not None and abs(r) >= self._min_r:
                        n = int(df.select([col_a, col_b]).drop_nulls().height)
                        results.append(CorrelationCoefficient(
                            value=round(float(r), 6),
                            column_a=col_a,
                            column_b=col_b,
                            method=CorrelationMethod.PEARSON,
                            sample_size=n,
                        ))
                except Exception:
                    continue
                if len(results) >= self._max_pairs:
                    break
        logger.info("correlation_computed", pairs=len(results), threshold=self._min_r)
        return sorted(results, key=lambda c: abs(c.value), reverse=True)

    def _compute_pandas(self, df, cols: list[str]) -> list[CorrelationCoefficient]:
        import numpy as np
        results = []
        sub = df[cols].dropna()
        for i, col_a in enumerate(cols):
            for col_b in cols[i+1:]:
                try:
                    r = np.corrcoef(sub[col_a], sub[col_b])[0, 1]
                    if not np.isnan(r) and abs(r) >= self._min_r:
                        results.append(CorrelationCoefficient(
                            value=round(float(r), 6),
                            column_a=col_a,
                            column_b=col_b,
                            method=CorrelationMethod.PEARSON,
                            sample_size=len(sub),
                        ))
                except Exception:
                    continue
        return sorted(results, key=lambda c: abs(c.value), reverse=True)
