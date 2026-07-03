"""Isolation Forest anomaly detector — model-based multivariate outlier detection.

Isolation Forest (Liu et al., 2008) builds an ensemble of random decision trees
that deliberately isolate observations. Anomalies are isolated faster (fewer
splits needed) than normal points because they are rare and distinct.

Advantages over Z-score and IQR:
  - Captures multivariate relationships between columns
  - Works on non-Gaussian and multi-modal distributions
  - No parametric assumptions; learns the data structure
  - ``contamination`` parameter controls expected anomaly proportion

Disadvantages:
  - Requires scikit-learn; heavier than IQR/Z-score
  - Slower on large datasets (sample first when n > 100k)
  - Harder to explain to a business user than "3 standard deviations above the mean"
  - Not reliable with < 50 rows

When to use:
  - Dataset has multiple numeric columns and you want cross-column detection
  - IQR and Z-score produce too many false positives on skewed data
  - ``FEATURE_ML_AGENT`` is enabled (Isolation Forest is the heavy hitter)

Usage::

    detector = IsolationForestDetector(contamination=0.05)
    results  = detector.detect_multivariate(df, numeric_columns=["revenue", "units", "margin"])
"""
from __future__ import annotations

from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)

# Maximum rows to pass to IsolationForest to keep memory bounded
_MAX_ROWS_FULL   = 50_000
_SAMPLE_FRACTION = 0.1   # fraction to use above _MAX_ROWS_FULL


@dataclass
class IFAnomaly:
    """One anomalous row flagged by Isolation Forest."""
    row_index:       int
    anomaly_score:   float    # raw decision function score; more negative = more anomalous
    confidence:      float    # normalised [0.5, 1.0]
    column_values:   dict[str, float] = field(default_factory=dict)


class IsolationForestDetector:
    """Multivariate anomaly detector using scikit-learn IsolationForest.

    Args:
        contamination: Fraction of data expected to be anomalous (default: 5%).
        n_estimators:  Number of trees in the forest (more = stable, slower).
        max_results:   Maximum anomalies to return.
    """

    def __init__(
        self,
        contamination: float = 0.05,
        n_estimators: int = 100,
        max_results: int = 200,
        random_state: int = 42,
    ) -> None:
        self._contamination = contamination
        self._n_estimators  = n_estimators
        self._max_results   = max_results
        self._random_state  = random_state

    def detect_multivariate(
        self,
        df,
        numeric_columns: list[str],
    ) -> list[IFAnomaly]:
        """Run Isolation Forest across multiple numeric columns simultaneously.

        Args:
            df:              DataFrame (polars or pandas).
            numeric_columns: List of numeric column names to include.

        Returns:
            List of ``IFAnomaly`` objects for flagged rows.
            Empty list when there are fewer than 50 rows or fewer than 2 columns.
        """
        if len(numeric_columns) < 2:
            return []

        try:
            return self._run(df, numeric_columns)
        except ImportError:
            logger.warning("isolation_forest_sklearn_unavailable")
            return []
        except Exception as exc:
            logger.warning("isolation_forest_failed", error=str(exc))
            return []

    def _run(self, df, columns: list[str]) -> list[IFAnomaly]:
        import numpy as np
        from sklearn.ensemble import IsolationForest as SKLearnIF
        from sklearn.preprocessing import StandardScaler

        # Extract numeric matrix — handle polars and pandas
        try:
            import polars as pl
            if isinstance(df, pl.DataFrame):
                data = df.select(columns).fill_null(0).to_numpy()
            else:
                data = df[columns].fillna(0).to_numpy()
        except Exception:
            data = df[columns].fillna(0).to_numpy()

        if data.shape[0] < 50 or data.shape[1] < 2:
            return []

        # Sample for very large datasets
        if data.shape[0] > _MAX_ROWS_FULL:
            rng         = np.random.default_rng(self._random_state)
            sample_size = int(data.shape[0] * _SAMPLE_FRACTION)
            indices     = rng.choice(data.shape[0], size=sample_size, replace=False)
            fit_data    = data[indices]
        else:
            fit_data = data

        # Fit and score
        scaler = StandardScaler()
        fit_scaled  = scaler.fit_transform(fit_data)
        full_scaled = scaler.transform(data)

        model = SKLearnIF(
            n_estimators=self._n_estimators,
            contamination=self._contamination,
            random_state=self._random_state,
            n_jobs=-1,   # use all CPU cores
        )
        model.fit(fit_scaled)
        scores    = model.decision_function(full_scaled)  # lower = more anomalous
        labels    = model.predict(full_scaled)            # -1 = anomaly, 1 = normal

        results   = []
        for idx, (label, score) in enumerate(zip(labels, scores)):
            if label == -1:
                # Normalise score to [0.5, 1.0] confidence
                # decision_function returns values around 0 for the boundary;
                # more negative = higher confidence anomaly
                confidence = min(1.0, 0.5 + abs(score) * 2)
                row_values = {col: float(data[idx, j]) for j, col in enumerate(columns)}
                results.append(IFAnomaly(
                    row_index=idx,
                    anomaly_score=round(float(score), 6),
                    confidence=round(confidence, 4),
                    column_values=row_values,
                ))
            if len(results) >= self._max_results:
                break

        results.sort(key=lambda x: x.anomaly_score)  # most anomalous first
        logger.info(
            "isolation_forest_complete",
            columns=columns,
            total_rows=data.shape[0],
            anomaly_count=len(results),
            contamination=self._contamination,
        )
        return results

    def to_anomaly_dicts(self, df, numeric_columns: list[str]) -> list[dict]:
        """Run detection and return plain dicts for the pipeline."""
        anomalies = self.detect_multivariate(df, numeric_columns)
        return [
            {
                "column":           "multivariate",
                "detection_method": "IsolationForest",
                "anomaly_type":     "outlier",
                "severity":         "medium" if a.confidence > 0.8 else "low",
                "confidence":       a.confidence,
                "rows_affected":    1,
                "value":            str(a.column_values),
                "row_index":        a.row_index,
                "description":      (
                    f"Row {a.row_index} is a multivariate outlier "
                    f"(Isolation Forest score {a.anomaly_score:.4f}). "
                    f"Unusual combination of values: "
                    f"{', '.join(f'{k}={v:.4g}' for k, v in list(a.column_values.items())[:3])}."
                ),
            }
            for a in anomalies
        ]
