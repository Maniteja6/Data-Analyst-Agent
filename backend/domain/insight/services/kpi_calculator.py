"""KPICalculator — domain service that derives KPI cards from a DataProfile."""

from __future__ import annotations


class KPICalculator:
    """Computes headline KPI cards from dataset profiling statistics.

    Each KPI is a dict with: name, value, unit, format, trend (reserved for
    period-over-period comparison, currently always None), and an optional
    benchmark used by the frontend to render a target line.
    """

    MAX_COLUMN_KPIS = 10

    def calculate(self, profile: dict) -> list[dict]:
        """Return the KPI cards for a dataset's InsightReport.

        Args:
            profile: DataProfile.to_dict()-shaped dict (row_count, column_count,
                completeness_score, duplicate_count, column_profiles).
        """
        kpis = [
            {
                "name": "Total Rows",
                "value": profile.get("row_count", 0),
                "unit": "rows",
                "format": "integer",
                "trend": None,
            },
            {
                "name": "Columns",
                "value": profile.get("column_count", 0),
                "unit": "cols",
                "format": "integer",
                "trend": None,
            },
            {
                "name": "Completeness",
                "value": round(profile.get("completeness_score", 1.0) * 100, 1),
                "unit": "%",
                "format": "percent",
                "trend": None,
                "benchmark": 95.0,
            },
            {
                "name": "Duplicate Rows",
                "value": profile.get("duplicate_count", 0),
                "unit": "rows",
                "format": "integer",
                "trend": None,
            },
        ]
        kpis.extend(self._column_kpis(profile))
        return kpis

    def _column_kpis(self, profile: dict) -> list[dict]:
        """Add one KPI per currency-typed numeric column, up to MAX_COLUMN_KPIS."""
        kpis = []
        for col in profile.get("column_profiles", []):
            stats = col.get("stats") or {}
            if not stats or col.get("kind") != "numeric":
                continue
            if col.get("semantic_type") == "currency":
                kpis.append(
                    {
                        "name": f"Avg {col['column_name']}",
                        "value": round(stats.get("mean", 0), 2),
                        "unit": "",
                        "format": "currency",
                        "trend": None,
                    }
                )
            if len(kpis) >= self.MAX_COLUMN_KPIS:
                break
        return kpis
