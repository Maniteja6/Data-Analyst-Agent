"""AnomalyAlert entity — a single classified anomaly raised during analysis."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from backend.shared.entity import Entity


class AnomalySeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AnomalyType(StrEnum):
    OUTLIER = "outlier"
    MISSING_PATTERN = "missing_pattern"
    SCHEMA_DRIFT = "schema_drift"
    RULE_VIOLATION = "rule_violation"
    DISTRIBUTION_SHIFT = "distribution_shift"


@dataclass
class AnomalyAlert(Entity):
    """A single anomaly detected in a dataset column, enriched with business context.

    Raised by AnomalyClassifier from raw detector output (ZScore, IQR,
    IsolationForest, or rule-based). Referenced by ID from
    ``AnalysisSession.anomaly_ids`` once persisted.

    Attributes:
        column_name:      Column the anomaly was detected in.
        anomaly_type:      Broad category of the anomaly.
        severity:          Business-impact severity, used to sort/filter alerts.
        description:       Human-readable explanation shown in the InsightReport.
        affected_rows:     Number of rows exhibiting the anomaly.
        detection_method:  Which detector raised this alert (ZScore | IQR |
                            IsolationForest | Rule).
        confidence:        Detector confidence, 0.0-1.0.
        raw_value:         Example anomalous value, if applicable.
        suggested_action:  Recommended remediation shown to the user.
    """

    column_name: str = ""
    anomaly_type: AnomalyType = AnomalyType.OUTLIER
    severity: AnomalySeverity = AnomalySeverity.LOW
    description: str = ""
    affected_rows: int = 0
    detection_method: str = ""
    confidence: float = 0.0
    raw_value: str | None = None
    suggested_action: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "column_name": self.column_name,
            "anomaly_type": self.anomaly_type.value,
            "severity": self.severity.value,
            "description": self.description,
            "affected_rows": self.affected_rows,
            "detection_method": self.detection_method,
            "confidence": self.confidence,
            "raw_value": self.raw_value,
            "suggested_action": self.suggested_action,
        }
