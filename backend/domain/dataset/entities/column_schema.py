"""ColumnSchema entity — one column in an inferred dataset schema."""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.shared.entity import Entity
from backend.domain.dataset.value_objects.semantic_type import SemanticType


@dataclass
class ColumnSchema(Entity):
    """Represents a single column as inferred by the Schema Agent.

    Stored as part of ``Dataset.schema_json`` (serialised to JSON) and
    returned to the frontend's schema table component. The Insight Agent
    and SQL Agent both read the schema to build grounded prompts.

    Attributes:
        name:           Raw column name as it appears in the file header.
        data_type:      Polars/pandas dtype string, e.g. ``'Float64'``, ``'Utf8'``.
        semantic_type:  Domain-level classification inferred by the Schema Agent.
        nullable:       True when at least one null/missing value was found.
        unique_count:   Number of distinct non-null values in the sample.
        missing_count:  Number of null cells in the sample window.
        missing_rate:   ``missing_count / sample_row_count`` (0.0 – 1.0).
        sample_values:  Up to 5 representative non-null values as strings.
        is_primary_key: True when the Schema Agent classifies this as the
                        most likely primary key (highest cardinality identifier).
    """

    name:           str
    data_type:      str
    semantic_type:  SemanticType = SemanticType.UNKNOWN
    nullable:       bool         = True
    unique_count:   int          = 0
    missing_count:  int          = 0
    missing_rate:   float        = 0.0
    sample_values:  list[str]    = field(default_factory=list)
    is_primary_key: bool         = False

    # ── Derived helpers ───────────────────────────────────────────────────

    @property
    def completeness(self) -> float:
        """Fraction of non-null values: ``1 - missing_rate``."""
        return round(1.0 - self.missing_rate, 6)

    @property
    def is_numeric(self) -> bool:
        return self.semantic_type.is_numeric

    @property
    def is_temporal(self) -> bool:
        return self.semantic_type.is_temporal

    @property
    def is_categorical(self) -> bool:
        return self.semantic_type == SemanticType.CATEGORICAL

    @property
    def is_high_cardinality(self) -> bool:
        """True when unique_count represents more than 80% of the sample.
        Used to detect identifier columns that should not be grouped.
        """
        return self.unique_count > 0 and self.missing_rate < 0.2 and self.is_primary_key

    @property
    def has_missing_values(self) -> bool:
        return self.missing_count > 0

    def to_dict(self) -> dict:
        """Serialise to the format stored in ``Dataset.schema_json['columns']``."""
        return {
            "id":            self.id,
            "name":          self.name,
            "data_type":     self.data_type,
            "semantic_type": self.semantic_type.value,
            "nullable":      self.nullable,
            "unique_count":  self.unique_count,
            "missing_count": self.missing_count,
            "missing_rate":  self.missing_rate,
            "completeness":  self.completeness,
            "sample_values": self.sample_values,
            "is_primary_key": self.is_primary_key,
        }
