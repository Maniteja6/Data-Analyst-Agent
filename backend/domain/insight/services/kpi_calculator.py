"""KPICalculator — domain service that derives KPI cards from a DataProfile."""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from backend.domain.insight.value_objects.kpi_value import KPIValue

logger = structlog.get_logger(__name__)


@dataclass
class KPI:
    """A single headline metric card shown on the InsightReport dashboard."""

    name: str
    value: KPIValue
    unit: str = ""
    format: str = "integer"  # integer | percent | currency
    trend: float | None = None
    benchmark: float | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value.raw,
            "unit": self.unit,
            "format": self.format,
            "trend": self.trend,
            "benchmark": self.benchmark,
        }


class KPICalculator:
    """Computes headline KPI cards from a DataProfile-shaped object.

    Accepts anything exposing ``row_count``, ``column_count``,
    ``completeness_score``, ``consistency_score``, ``duplicate_count``, and
    ``column_profiles`` — duck-typed so callers can pass either the real
    ``DataProfile`` entity or a lightweight test double.
    """

    MAX_COLUMN_KPIS = 10

    @staticmethod
    def _attr(obj: object, name: str, default: float) -> float:
        """getattr() with a default that also covers __getattr__ implementations
        that return None for unknown attributes instead of raising."""
        value = getattr(obj, name, default)
        return default if value is None else value

    def calculate(self, report_id: str, profile: object) -> list[KPI]:
        """Return the KPI cards for an InsightReport.

        Args:
            report_id: InsightReport these KPIs belong to (used for tracing).
            profile:   DataProfile-like object with row_count, column_count,
                completeness_score, consistency_score, duplicate_count, and
                column_profiles attributes.
        """
        kpis = [
            KPI(
                name="Total Rows",
                value=KPIValue(raw=float(self._attr(profile, "row_count", 0))),
                unit="rows",
            ),
            KPI(
                name="Columns",
                value=KPIValue(raw=float(self._attr(profile, "column_count", 0))),
                unit="cols",
            ),
            KPI(
                name="Completeness",
                value=KPIValue(raw=round(self._attr(profile, "completeness_score", 1.0) * 100, 1)),
                unit="%",
                format="percent",
                benchmark=95.0,
            ),
            KPI(
                name="Consistency",
                value=KPIValue(raw=round(self._attr(profile, "consistency_score", 1.0) * 100, 1)),
                unit="%",
                format="percent",
                benchmark=95.0,
            ),
            KPI(
                name="Duplicate Rows",
                value=KPIValue(raw=float(self._attr(profile, "duplicate_count", 0))),
                unit="rows",
            ),
        ]
        kpis.extend(self._column_kpis(profile))
        logger.debug("kpis_calculated", report_id=report_id, kpi_count=len(kpis))
        return kpis

    def _column_kpis(self, profile: object) -> list[KPI]:
        """Add one KPI per currency-typed column, up to MAX_COLUMN_KPIS."""
        kpis: list[KPI] = []
        for col in getattr(profile, "column_profiles", None) or []:
            if getattr(col, "semantic_type", None) != "currency":
                continue
            stats = getattr(col, "stats", None)
            mean = getattr(stats, "mean", None) if stats is not None else None
            if mean is None:
                continue
            kpis.append(
                KPI(
                    name=f"Avg {col.column_name}",
                    value=KPIValue(raw=round(mean, 2)),
                    format="currency",
                )
            )
            if len(kpis) >= self.MAX_COLUMN_KPIS:
                break
        return kpis
