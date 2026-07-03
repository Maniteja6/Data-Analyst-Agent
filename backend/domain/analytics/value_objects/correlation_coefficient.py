"""CorrelationCoefficient value object — a validated Pearson or Spearman r value."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.shared.value_object import ValueObject


class CorrelationMethod(str, Enum):
    PEARSON  = "pearson"
    SPEARMAN = "spearman"
    KENDALL  = "kendall"


@dataclass(frozen=True)
class CorrelationCoefficient(ValueObject):
    """A validated correlation coefficient in the range [-1, 1].

    Used inside ``DataProfile`` to represent pairwise column correlations.
    The Insight agent uses strong correlations to generate business insights
    (e.g. "revenue is strongly positively correlated with units_sold").
    """

    value: float
    column_a: str
    column_b: str
    method: CorrelationMethod = CorrelationMethod.PEARSON
    sample_size: int = 0

    def _validate(self) -> None:
        if not -1.0 <= self.value <= 1.0:
            raise ValueError(
                f"Correlation coefficient must be in [-1, 1], got {self.value}"
            )
        if not self.column_a or not self.column_b:
            raise ValueError("column_a and column_b must not be empty")

    # ── Strength classification ───────────────────────────────────────────

    @property
    def abs_value(self) -> float:
        return abs(self.value)

    @property
    def strength(self) -> str:
        """Returns a human-readable strength label."""
        v = self.abs_value
        if v >= 0.9:
            return "very strong"
        if v >= 0.7:
            return "strong"
        if v >= 0.5:
            return "moderate"
        if v >= 0.3:
            return "weak"
        return "negligible"

    @property
    def direction(self) -> str:
        if self.value > 0:
            return "positive"
        if self.value < 0:
            return "negative"
        return "none"

    @property
    def is_significant(self) -> bool:
        """True when |r| >= 0.3 — threshold used by the Insight agent."""
        return self.abs_value >= 0.3

    def describe(self) -> str:
        """Human-readable description suitable for use in an insight headline."""
        return (
            f"'{self.column_a}' and '{self.column_b}' have a "
            f"{self.strength} {self.direction} {self.method} correlation "
            f"(r={self.value:.3f})"
        )
