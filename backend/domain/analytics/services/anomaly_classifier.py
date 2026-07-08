"""AnomalyClassifier — domain service that classifies raw detector output
into typed AnomalyAlert entities with severity and business context."""

from __future__ import annotations

from backend.domain.analytics.entities.anomaly_alert import (
    AnomalyAlert,
    AnomalySeverity,
    AnomalyType,
)


class AnomalyClassifier:
    """Classifies raw detector dicts into ``AnomalyAlert`` entities.

    Rules:
    - Z-score |z| > 5   → HIGH,   |z| 3-5 → MEDIUM
    - IQR outliers       → LOW
    - Isolation Forest   → MEDIUM
    - Rule violations (negative price etc.) → HIGH
    - Very high confidence (>0.9) escalates one severity level
    """

    ESCALATION_CONFIDENCE_THRESHOLD = 0.9

    def classify(self, raw: dict) -> AnomalyAlert:
        method = raw.get("detection_method", "Unknown")
        base_sev = self._base_severity(raw)
        confidence = float(raw.get("confidence", 0.7))

        # Escalate severity for very high-confidence findings
        if confidence >= self.ESCALATION_CONFIDENCE_THRESHOLD:
            base_sev = self._escalate(base_sev)

        description = raw.get(
            "description", f"Anomaly detected in column '{raw.get('column', '')}'"
        )
        suggested = self._suggest_action(raw.get("anomaly_type", "outlier"), raw.get("column", ""))

        return AnomalyAlert(
            column_name=raw.get("column", "__unknown__"),
            anomaly_type=AnomalyType(raw.get("anomaly_type", "outlier")),
            severity=base_sev,
            description=description,
            affected_rows=int(raw.get("rows_affected", 1)),
            detection_method=method,
            confidence=confidence,
            raw_value=raw.get("value"),
            suggested_action=suggested,
        )

    def classify_batch(self, raw_list: list[dict]) -> list[AnomalyAlert]:
        return [self.classify(r) for r in raw_list]

    # ── Private helpers ───────────────────────────────────────────────────

    def _base_severity(self, raw: dict) -> AnomalySeverity:
        method = raw.get("detection_method", "")
        raw_severity = raw.get("severity", "")

        if raw_severity == "critical":
            return AnomalySeverity.CRITICAL
        if raw_severity == "high" or raw.get("anomaly_type") == "rule_violation":
            return AnomalySeverity.HIGH
        if method == "ZScore" and raw.get("confidence", 0) > 0.85:
            return AnomalySeverity.HIGH
        if method in ("ZScore", "IsolationForest"):
            return AnomalySeverity.MEDIUM
        return AnomalySeverity.LOW

    @staticmethod
    def _escalate(severity: AnomalySeverity) -> AnomalySeverity:
        order = [
            AnomalySeverity.LOW,
            AnomalySeverity.MEDIUM,
            AnomalySeverity.HIGH,
            AnomalySeverity.CRITICAL,
        ]
        idx = order.index(severity)
        return order[min(idx + 1, len(order) - 1)]

    @staticmethod
    def _suggest_action(anomaly_type: str, column: str) -> str:
        suggestions = {
            "outlier": (f"Investigate outlier values in '{column}'; consider capping or removal."),
            "rule_violation": (
                f"Review data entry validation for '{column}' — invalid values detected."
            ),
            "missing_pattern": (
                f"Check upstream data pipeline for '{column}'; "
                f"systematic nulls may indicate an ETL issue."
            ),
            "distribution_shift": (
                f"'{column}' distribution has shifted; verify data source consistency."
            ),
        }
        return suggestions.get(anomaly_type, "Review flagged rows for data quality issues.")
