"""Histogram value object — discrete frequency distribution for a column."""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.shared.value_object import ValueObject


@dataclass(frozen=True)
class HistogramBin(ValueObject):
    """One bin in a histogram."""

    label: str          # e.g. "10.0-20.0" for numeric, "London" for categorical
    count: int
    frequency: float    # count / total (0.0 – 1.0)

    def _validate(self) -> None:
        if self.count < 0:
            raise ValueError("Histogram bin count must be non-negative")
        if not 0.0 <= self.frequency <= 1.0:
            raise ValueError(f"Histogram frequency must be in [0, 1], got {self.frequency}")


@dataclass(frozen=True)
class Histogram(ValueObject):
    """Frequency distribution for a single dataset column.

    For numeric columns bins are equal-width ranges.
    For categorical columns each bin is one distinct value.

    Stored as a value object inside ``ColumnProfile`` and serialised to
    JSON for the frontend histogram chart component.
    """

    column_name: str
    bins: tuple[HistogramBin, ...]   # tuple keeps the VO frozen/hashable
    total_count: int
    bin_type: str = "numeric"        # "numeric" | "categorical" | "datetime"

    def _validate(self) -> None:
        if not self.column_name:
            raise ValueError("column_name must not be empty")
        if self.total_count < 0:
            raise ValueError("total_count must be non-negative")

    @classmethod
    def from_value_counts(
        cls,
        column_name: str,
        counts: dict[str, int],
        top_n: int = 20,
    ) -> "Histogram":
        """Build a categorical histogram from a {value: count} dict.

        Args:
            column_name: Column this histogram belongs to.
            counts:      Value → frequency dict (e.g. from polars value_counts).
            top_n:       Keep only the top N bins by count.
        """
        total = sum(counts.values())
        sorted_bins = sorted(counts.items(), key=lambda x: -x[1])[:top_n]
        bins = tuple(
            HistogramBin(
                label=str(label),
                count=count,
                frequency=round(count / total, 6) if total else 0.0,
            )
            for label, count in sorted_bins
        )
        return cls(
            column_name=column_name,
            bins=bins,
            total_count=total,
            bin_type="categorical",
        )

    @classmethod
    def from_numeric_ranges(
        cls,
        column_name: str,
        bin_edges: list[float],
        bin_counts: list[int],
    ) -> "Histogram":
        """Build a numeric histogram from pre-computed bin edges and counts."""
        total = sum(bin_counts)
        bins = tuple(
            HistogramBin(
                label=f"{bin_edges[i]:.4g}-{bin_edges[i + 1]:.4g}",
                count=bin_counts[i],
                frequency=round(bin_counts[i] / total, 6) if total else 0.0,
            )
            for i in range(len(bin_counts))
        )
        return cls(
            column_name=column_name,
            bins=bins,
            total_count=total,
            bin_type="numeric",
        )

    def to_list(self) -> list[dict]:
        """Serialise to the list-of-dicts format expected by the frontend chart."""
        return [{"bin": b.label, "count": b.count, "pct": b.frequency} for b in self.bins]

    @property
    def most_frequent_bin(self) -> HistogramBin | None:
        return max(self.bins, key=lambda b: b.count) if self.bins else None
