"""ColumnProfile entity — statistical profile of one dataset column."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from backend.shared.entity import Entity
from backend.domain.analytics.value_objects.statistical_summary import StatisticalSummary
from backend.domain.analytics.value_objects.histogram import Histogram


class ColumnKind(str, Enum):
    """Broad runtime type — used to decide which profiler to invoke."""
    NUMERIC   = "numeric"
    DATETIME  = "datetime"
    TEXT      = "text"
    BOOLEAN   = "boolean"
    UNKNOWN   = "unknown"


@dataclass
class ColumnProfile(Entity):
    """Statistical profile for a single column in a dataset.

    Produced by the profiling pipeline and stored on ``DataProfile``.
    The Schema Agent reads ``sample_values`` and ``top_values`` to infer
    the semantic type; the Insight Agent uses the stats to generate
    business-relevant observations.

    Attributes:
        session_id:       Parent AnalysisSession identifier.
        column_name:      Raw column name as it appears in the dataset.
        data_type:        Polars/pandas dtype string, e.g. ``'Float64'``, ``'Utf8'``.
        semantic_type:    Domain-level type inferred by the Schema Agent.
        kind:             Broad runtime category (numeric / datetime / text / boolean).
        total_rows:       Total row count including nulls.
        null_count:       Number of null / missing values.
        unique_count:     Number of distinct non-null values.
        stats:            Descriptive statistics (numeric columns only).
        histogram:        Frequency distribution (numeric and categorical).
        sample_values:    Up to 5 non-null sample values as strings.
        top_values:       Top-N most frequent values with counts.
    """

    session_id:    str
    column_name:   str
    data_type:     str
    semantic_type: str           = "unknown"
    kind:          ColumnKind    = ColumnKind.UNKNOWN
    total_rows:    int           = 0
    null_count:    int           = 0
    unique_count:  int           = 0
    stats:         StatisticalSummary | None = None
    histogram:     Histogram | None          = None
    sample_values: list[str]     = field(default_factory=list)
    top_values:    list[dict]    = field(default_factory=list)   # [{"value": x, "count": n, "pct": 0.x}]

    # ── Derived properties ────────────────────────────────────────────────

    @property
    def null_rate(self) -> float:
        """Fraction of rows that are null (0.0 – 1.0)."""
        if self.total_rows == 0:
            return 0.0
        return round(self.null_count / self.total_rows, 6)

    @property
    def completeness(self) -> float:
        """Fraction of rows that are non-null (1 - null_rate)."""
        return round(1.0 - self.null_rate, 6)

    @property
    def cardinality_ratio(self) -> float:
        """Unique count / total non-null rows.

        A ratio near 1.0 suggests an identifier column.
        A very low ratio suggests a categorical column.
        """
        non_null = self.total_rows - self.null_count
        if non_null == 0:
            return 0.0
        return round(self.unique_count / non_null, 6)

    @property
    def is_high_cardinality(self) -> bool:
        """True when the column has > 50% unique values — likely an ID or free text."""
        return self.cardinality_ratio > 0.5

    @property
    def is_constant(self) -> bool:
        """True when all non-null values are identical."""
        return self.unique_count == 1

    def to_dict(self) -> dict:
        """Serialise to a plain dict for JSON transport to the frontend / agents."""
        return {
            "id":              self.id,
            "column_name":     self.column_name,
            "data_type":       self.data_type,
            "semantic_type":   self.semantic_type,
            "kind":            self.kind.value,
            "total_rows":      self.total_rows,
            "null_count":      self.null_count,
            "null_rate":       self.null_rate,
            "unique_count":    self.unique_count,
            "completeness":    self.completeness,
            "sample_values":   self.sample_values,
            "top_values":      self.top_values,
            "stats":           self.stats.to_dict() if self.stats else None,
            "histogram":       self.histogram.to_list() if self.histogram else [],
        }
