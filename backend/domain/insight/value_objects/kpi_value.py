"""KPIValue value object — the numeric value behind a KPI card."""

from __future__ import annotations

from dataclasses import dataclass

from backend.shared.value_object import ValueObject


@dataclass(frozen=True)
class KPIValue(ValueObject):
    """The raw numeric value backing a KPI, decoupled from display formatting.

    Kept separate from ``KPI`` (name, unit, format, trend) so the number
    itself can be compared/tested independently of how it's presented.
    """

    raw: float
