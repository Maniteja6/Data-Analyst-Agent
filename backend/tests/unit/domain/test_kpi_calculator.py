"""Unit tests for KPICalculator."""

import pytest
from backend.domain.insight.services.kpi_calculator import KPICalculator


@pytest.mark.unit
class TestKPICalculator:
    def setup_method(self) -> None:
        self.calc = KPICalculator()

    def _make_profile(
        self, rows=100, cols=5, completeness=0.95, consistency=0.98, col_profiles=None
    ):
        class _P:
            row_count = rows
            column_count = cols
            completeness_score = completeness
            consistency_score = consistency
            duplicate_count = int(rows * (1 - consistency))
            column_profiles = col_profiles or []

        return _P()

    def test_basic_kpis_produced(self) -> None:
        profile = self._make_profile()
        kpis = self.calc.calculate("report-1", profile)
        names = [k.name for k in kpis]
        assert "Total Rows" in names
        assert "Columns" in names
        assert "Completeness" in names
        assert "Consistency" in names

    def test_kpi_values_match_profile(self) -> None:
        profile = self._make_profile(rows=500, completeness=0.90)
        kpis = self.calc.calculate("report-1", profile)
        row_kpi = next(k for k in kpis if k.name == "Total Rows")
        assert row_kpi.value.raw == 500.0

    def test_currency_column_produces_avg_kpi(self) -> None:
        class _Stats:
            mean = 1234.56

        class _CurrencyCol:
            column_name = "revenue"
            semantic_type = "currency"
            stats = _Stats()

        profile = self._make_profile(col_profiles=[_CurrencyCol()])
        kpis = self.calc.calculate("r", profile)
        names = [k.name for k in kpis]
        assert "Avg revenue" in names
