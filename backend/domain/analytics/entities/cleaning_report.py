"""CleaningReport entity — audit record of the data cleaning pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from backend.shared.entity import Entity


class CleaningAction(str, Enum):
    """Types of cleaning operations that can be applied to a dataset."""
    REMOVE_DUPLICATES  = "remove_duplicates"
    IMPUTE_MEDIAN      = "impute_median"
    IMPUTE_MEAN        = "impute_mean"
    IMPUTE_MODE        = "impute_mode"
    IMPUTE_CONSTANT    = "impute_constant"
    DROP_HIGH_NULL_COL = "drop_column_high_null"
    COERCE_TO_FLOAT    = "coerce_to_float"
    COERCE_TO_DATETIME = "coerce_to_datetime"
    FLAG_OUTLIER       = "flag_outlier"
    CLIP_OUTLIER       = "clip_outlier"
    STRIP_WHITESPACE   = "strip_whitespace"


@dataclass
class CleaningStep:
    """Records one atomic cleaning action applied to the dataset."""

    action:        CleaningAction
    column:        str | None       # None for row-level actions (e.g. duplicate removal)
    rows_affected: int              = 0
    description:   str              = ""
    before_value:  str | None       = None  # sample value before cleaning
    after_value:   str | None       = None  # sample value after cleaning


@dataclass
class CleaningReport(Entity):
    """Immutable audit trail of every transformation applied during cleaning.

    Stored on the AnalysisSession and surfaced to users via the Data Quality
    page so they can understand exactly what was changed before analysis.

    Attributes:
        session_id:      Parent AnalysisSession.
        dataset_id:      Source dataset.
        rows_before:     Row count before any cleaning steps.
        rows_after:      Row count after removing duplicates.
        columns_before:  Column count before dropping high-null columns.
        columns_after:   Column count after dropping.
        steps:           Ordered list of cleaning operations applied.
        cleaned_at:      UTC timestamp when cleaning completed.
    """

    session_id:     str
    dataset_id:     str
    rows_before:    int
    rows_after:     int
    columns_before: int
    columns_after:  int
    steps:          list[CleaningStep] = field(default_factory=list)
    cleaned_at:     datetime | None    = None

    # ── Derived helpers ───────────────────────────────────────────────────

    @property
    def rows_removed(self) -> int:
        return max(0, self.rows_before - self.rows_after)

    @property
    def columns_removed(self) -> int:
        return max(0, self.columns_before - self.columns_after)

    @property
    def duplicates_removed(self) -> int:
        return sum(
            s.rows_affected for s in self.steps
            if s.action == CleaningAction.REMOVE_DUPLICATES
        )

    @property
    def imputed_columns(self) -> list[str]:
        """Column names where missing values were imputed."""
        impute_actions = {
            CleaningAction.IMPUTE_MEDIAN,
            CleaningAction.IMPUTE_MEAN,
            CleaningAction.IMPUTE_MODE,
            CleaningAction.IMPUTE_CONSTANT,
        }
        return list({
            s.column for s in self.steps
            if s.action in impute_actions and s.column
        })

    @property
    def dropped_columns(self) -> list[str]:
        """Column names dropped due to excessive nulls."""
        return [
            s.column for s in self.steps
            if s.action == CleaningAction.DROP_HIGH_NULL_COL and s.column
        ]

    def to_dict(self) -> dict:
        return {
            "id":             self.id,
            "session_id":     self.session_id,
            "dataset_id":     self.dataset_id,
            "rows_before":    self.rows_before,
            "rows_after":     self.rows_after,
            "rows_removed":   self.rows_removed,
            "columns_before": self.columns_before,
            "columns_after":  self.columns_after,
            "columns_removed": self.columns_removed,
            "duplicates_removed": self.duplicates_removed,
            "imputed_columns": self.imputed_columns,
            "dropped_columns": self.dropped_columns,
            "step_count":     len(self.steps),
            "steps":          [
                {
                    "action":        s.action.value,
                    "column":        s.column,
                    "rows_affected": s.rows_affected,
                    "description":   s.description,
                }
                for s in self.steps
            ],
            "cleaned_at": self.cleaned_at.isoformat() if self.cleaned_at else None,
        }
