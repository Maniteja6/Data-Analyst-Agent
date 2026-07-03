"""DataProfile entity — full statistical profile of a dataset."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from backend.shared.entity import Entity
from backend.domain.analytics.entities.column_profile import ColumnProfile
from backend.domain.analytics.value_objects.correlation_coefficient import CorrelationCoefficient


@dataclass
class DataProfile(Entity):
    """Full statistical profile produced for one AnalysisSession.

    One DataProfile is created per analysis run and stores the output of
    the numeric, categorical, datetime, and text profilers for every
    column in the dataset. The Insight Agent reads the profile to generate
    KPIs, executive summary, and anomaly context.

    Attributes:
        session_id:           Parent AnalysisSession.
        dataset_id:           Source dataset.
        row_count:            Total rows in the dataset (before cleaning).
        column_count:         Total columns.
        duplicate_count:      Exact duplicate rows detected.
        completeness_score:   Fraction of non-null cells across the whole dataset (0–1).
        consistency_score:    1 - (duplicate_count / row_count).
        column_profiles:      Per-column profiling results.
        correlations:         Significant pairwise correlation coefficients.
        profiled_at:          UTC timestamp when profiling completed.
    """

    session_id:         str
    dataset_id:         str
    row_count:          int
    column_count:       int
    duplicate_count:    int                          = 0
    completeness_score: float                        = 1.0
    consistency_score:  float                        = 1.0
    column_profiles:    list[ColumnProfile]          = field(default_factory=list)
    correlations:       list[CorrelationCoefficient] = field(default_factory=list)
    profiled_at:        datetime | None              = None

    # ── Derived helpers ───────────────────────────────────────────────────

    @property
    def overall_quality_score(self) -> float:
        """Composite quality score — simple average of completeness and consistency."""
        return round((self.completeness_score + self.consistency_score) / 2, 4)

    @property
    def quality_grade(self) -> str:
        """Letter grade for the overall data quality score."""
        score = self.overall_quality_score
        if score >= 0.95:
            return "A"
        if score >= 0.85:
            return "B"
        if score >= 0.70:
            return "C"
        if score >= 0.55:
            return "D"
        return "F"

    def get_column(self, name: str) -> ColumnProfile | None:
        """Find a ColumnProfile by column name (case-sensitive)."""
        return next((c for c in self.column_profiles if c.column_name == name), None)

    @property
    def numeric_columns(self) -> list[ColumnProfile]:
        from backend.domain.analytics.entities.column_profile import ColumnKind
        return [c for c in self.column_profiles if c.kind == ColumnKind.NUMERIC]

    @property
    def datetime_columns(self) -> list[ColumnProfile]:
        from backend.domain.analytics.entities.column_profile import ColumnKind
        return [c for c in self.column_profiles if c.kind == ColumnKind.DATETIME]

    @property
    def categorical_columns(self) -> list[ColumnProfile]:
        from backend.domain.analytics.entities.column_profile import ColumnKind
        return [c for c in self.column_profiles if c.kind == ColumnKind.TEXT]

    @property
    def has_time_series(self) -> bool:
        """True when the dataset has at least one datetime column."""
        return len(self.datetime_columns) > 0

    @property
    def significant_correlations(self) -> list[CorrelationCoefficient]:
        """Correlations with |r| >= 0.3 — used by the Insight Agent."""
        return [c for c in self.correlations if c.is_significant]

    def to_dict(self) -> dict:
        return {
            "id":                 self.id,
            "session_id":         self.session_id,
            "dataset_id":         self.dataset_id,
            "row_count":          self.row_count,
            "column_count":       self.column_count,
            "duplicate_count":    self.duplicate_count,
            "completeness_score": self.completeness_score,
            "consistency_score":  self.consistency_score,
            "overall_quality":    self.overall_quality_score,
            "quality_grade":      self.quality_grade,
            "has_time_series":    self.has_time_series,
            "column_profiles":    [c.to_dict() for c in self.column_profiles],
            "profiled_at":        self.profiled_at.isoformat() if self.profiled_at else None,
        }
