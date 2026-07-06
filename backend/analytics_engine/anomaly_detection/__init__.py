"""Anomaly detection sub-package — IQR, Z-score, Isolation Forest, and rule-based detectors."""
"""Anomaly detection — multi-method outlier identification.

AnomalyDetector:         orchestrator; deduplicates + ranks by severity + confidence.
ZScoreDetector:          |z| >= threshold; polars-first, pandas fallback.
IQRDetector:             Tukey fence; multiplier configurable (default 1.5).
IsolationForestDetector: sklearn multivariate; samples to 10% on large datasets.
RuleDetector:            semantic rules — negative currency, % out of range, future dates.
"""
from backend.analytics_engine.anomaly_detection.anomaly_detector import AnomalyDetector

__all__ = ["AnomalyDetector"]
