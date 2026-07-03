"""DataQualityScorer — domain service that computes the composite quality score."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class QualityDimension:
    """Score and weight for one quality dimension."""
    name:   str
    score:  float    # 0.0 – 1.0
    weight: float    # contribution weight (all weights should sum to 1.0)


@dataclass
class QualityReport:
    """Full quality report for a dataset profile."""
    overall_score:      float
    grade:              str
    dimensions:         list[QualityDimension]
    completeness_score: float
    consistency_score:  float
    validity_score:     float
    timeliness_score:   float


class DataQualityScorer:
    """Computes a composite data quality score from a ``DataProfile``.

    Dimensions and weights:
    - Completeness  (40%) — fraction of non-null cells
    - Consistency   (30%) — 1 - duplicate row rate
    - Validity      (20%) — fraction of columns with acceptable null rate (< 20%)
    - Timeliness    (10%) — 1.0 if datetime columns are present, 0.5 otherwise

    These weights can be tuned per deployment via the feature-flags system.
    """

    WEIGHTS = {
        "completeness": 0.40,
        "consistency":  0.30,
        "validity":     0.20,
        "timeliness":   0.10,
    }

    def score(self, profile) -> QualityReport:
        """Compute the quality report from a ``DataProfile`` object.

        Args:
            profile: A ``DataProfile`` entity (or any duck-typed object with
                     the same attributes).
        """
        completeness = float(getattr(profile, "completeness_score", 1.0))
        consistency  = float(getattr(profile, "consistency_score",  1.0))
        validity     = self._validity_score(profile)
        timeliness   = self._timeliness_score(profile)

        dimensions = [
            QualityDimension("Completeness", completeness, self.WEIGHTS["completeness"]),
            QualityDimension("Consistency",  consistency,  self.WEIGHTS["consistency"]),
            QualityDimension("Validity",     validity,     self.WEIGHTS["validity"]),
            QualityDimension("Timeliness",   timeliness,   self.WEIGHTS["timeliness"]),
        ]

        overall = sum(d.score * d.weight for d in dimensions)
        overall = round(overall, 4)

        return QualityReport(
            overall_score=overall,
            grade=self._grade(overall),
            dimensions=dimensions,
            completeness_score=completeness,
            consistency_score=consistency,
            validity_score=validity,
            timeliness_score=timeliness,
        )

    # ── Dimension calculators ─────────────────────────────────────────────

    @staticmethod
    def _validity_score(profile) -> float:
        """Fraction of columns whose null rate is below 20%."""
        cols = getattr(profile, "column_profiles", [])
        if not cols:
            return 1.0
        valid = sum(
            1 for c in cols
            if getattr(c, "null_rate", 0.0) < 0.20
        )
        return round(valid / len(cols), 4)

    @staticmethod
    def _timeliness_score(profile) -> float:
        """1.0 when datetime columns are present (data is time-aware), 0.5 otherwise."""
        datetime_cols = getattr(profile, "datetime_columns", [])
        return 1.0 if datetime_cols else 0.5

    @staticmethod
    def _grade(score: float) -> str:
        if score >= 0.95:
            return "A"
        if score >= 0.85:
            return "B"
        if score >= 0.70:
            return "C"
        if score >= 0.55:
            return "D"
        return "F"
