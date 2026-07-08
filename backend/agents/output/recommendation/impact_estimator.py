"""ImpactEstimator — estimates the quantified business impact of a recommendation.

Real-time design:
    Each recommendation is enriched with an estimated impact range before
    being emitted as a ``recommendation:ready`` Socket.IO event. This
    gives the frontend data to render confidence bars and ROI indicators
    without waiting for the full report to complete.

Estimation strategy:
    A heuristic scoring model assigns impact ranges based on:
    1. The business_impact field of the source insight (high/medium/low)
    2. The semantic type of the primary affected column (currency → revenue impact)
    3. The anomaly count (more anomalies → larger risk reduction opportunity)
    4. Whether a forecast trend was provided (upward trend → growth opportunity)

    These heuristics are intentionally conservative (lower-bound estimates)
    to avoid overpromising in executive reports.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

# Base impact ranges by insight severity (percentage improvement estimates)
_IMPACT_RANGES = {
    "high": {"min_pct": 10.0, "max_pct": 25.0, "label": "Significant"},
    "medium": {"min_pct": 3.0, "max_pct": 10.0, "label": "Moderate"},
    "low": {"min_pct": 1.0, "max_pct": 5.0, "label": "Minor"},
}

# Semantic type multipliers (currency columns have higher revenue impact)
_TYPE_MULTIPLIERS = {
    "currency": 1.5,
    "numeric_measure": 1.2,
    "numeric_count": 1.0,
    "categorical": 0.8,
    "percentage": 1.1,
}


class ImpactEstimator:
    """Estimates quantified impact ranges for recommendations."""

    def estimate(
        self,
        recommendation: dict,
        source_insight: dict | None = None,
        column_semantic_types: dict[str, str] | None = None,
        anomaly_count: int = 0,
        forecast_trend: str = "",
    ) -> dict:
        """Estimate the business impact of one recommendation.

        Args:
            recommendation:       Dict with at least ``priority`` key.
            source_insight:       The insight that triggered this recommendation.
            column_semantic_types: {col_name: semantic_type} for type multipliers.
            anomaly_count:        Number of detected anomalies.
            forecast_trend:       "up" | "down" | "flat" | "unknown".

        Returns:
            Dict with keys: min_pct, max_pct, label, confidence, rationale.
        """
        priority = recommendation.get("priority", "medium").lower()
        base = _IMPACT_RANGES.get(priority, _IMPACT_RANGES["medium"])

        min_pct = base["min_pct"]
        max_pct = base["max_pct"]
        label = base["label"]

        # Apply semantic type multiplier for the primary source column
        if source_insight and column_semantic_types:
            source_cols = source_insight.get("source_columns", [])
            primary_col = source_cols[0] if source_cols else ""
            stype = (column_semantic_types or {}).get(primary_col, "unknown")
            multiplier = _TYPE_MULTIPLIERS.get(stype, 1.0)
            min_pct = round(min_pct * multiplier, 1)
            max_pct = round(max_pct * multiplier, 1)

        # Anomaly bonus: more anomalies = larger risk reduction opportunity
        if anomaly_count > 10:
            min_pct = round(min_pct * 1.2, 1)
            max_pct = round(max_pct * 1.2, 1)

        # Forecast trend modifier
        if forecast_trend == "up":
            max_pct = round(max_pct * 1.15, 1)  # growth opportunity
        elif forecast_trend == "down":
            min_pct = round(min_pct * 1.10, 1)  # risk mitigation

        # Confidence based on data quality
        confidence = 0.75
        if source_insight:
            confidence = min(0.90, float(source_insight.get("confidence", 0.75)))

        rationale = self._build_rationale(
            recommendation, source_insight, min_pct, max_pct, anomaly_count, forecast_trend
        )

        result = {
            "min_pct": min_pct,
            "max_pct": max_pct,
            "label": label,
            "confidence": confidence,
            "rationale": rationale,
        }
        logger.debug(
            "impact_estimated",
            priority=priority,
            min=min_pct,
            max=max_pct,
            confidence=confidence,
        )
        return result

    @staticmethod
    def _build_rationale(
        rec: dict,
        insight: dict | None,
        min_pct: float,
        max_pct: float,
        anomaly_count: int,
        forecast_trend: str,
    ) -> str:
        """Build a one-sentence explanation of the impact estimate."""
        action = rec.get("action", "This action")[:80]
        if insight:
            return (
                f"{action} is estimated to deliver a {min_pct:.0f}–{max_pct:.0f}% "
                f"improvement based on the '{insight.get('headline', 'key finding')}' "
                f"finding."
            )
        return (
            f"Estimated {min_pct:.0f}–{max_pct:.0f}% improvement potential "
            f"based on analysis of {anomaly_count} data quality issues "
            f"and {forecast_trend} trend direction."
        )

    def batch_estimate(
        self,
        recommendations: list[dict],
        insights: list[dict],
        schema: dict | None = None,
        anomaly_count: int = 0,
        forecast_trend: str = "unknown",
    ) -> list[dict]:
        """Estimate impact for a list of recommendations, matched to insights.

        Attaches ``estimated_impact`` dict to each recommendation in place.
        Returns the updated list.
        """
        col_types: dict[str, str] = {}
        if schema:
            col_types = {
                c["name"]: c.get("semantic_type", "unknown") for c in schema.get("columns", [])
            }

        # Map insight indices to recommendations (1:1 by position)
        for i, rec in enumerate(recommendations):
            insight = insights[i] if i < len(insights) else None
            impact = self.estimate(
                recommendation=rec,
                source_insight=insight,
                column_semantic_types=col_types,
                anomaly_count=anomaly_count,
                forecast_trend=forecast_trend,
            )
            rec["estimated_impact"] = impact

        return recommendations
