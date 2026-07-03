"""Unit tests for forecast-related components."""
import pytest


@pytest.mark.unit
class TestTrendAnalyzer:

    def test_detects_increasing_trend(self):
        from backend.analytics_engine.statistics.trend_analyzer import TrendAnalyzer
        import pandas as pd

        df = pd.DataFrame({
            "date":  [f"2024-01-{i+1:02d}" for i in range(10)],
            "sales": [100 + i * 50 for i in range(10)],
        })
        result = TrendAnalyzer().detect_trend(df, "date", "sales")
        assert result["direction"] == "increasing"
        assert result["r_squared"] > 0.9

    def test_detects_flat_trend(self):
        from backend.analytics_engine.statistics.trend_analyzer import TrendAnalyzer
        import pandas as pd

        df = pd.DataFrame({
            "date":  [f"2024-01-{i+1:02d}" for i in range(10)],
            "sales": [500.0] * 10,
        })
        result = TrendAnalyzer().detect_trend(df, "date", "sales")
        # Flat — slope should be near 0
        assert abs(result.get("slope", 1)) < 0.01

    def test_insufficient_data_returns_empty(self):
        from backend.analytics_engine.statistics.trend_analyzer import TrendAnalyzer
        import pandas as pd

        df = pd.DataFrame({"date": ["2024-01-01", "2024-01-02"], "v": [1, 2]})
        result = TrendAnalyzer().detect_trend(df, "date", "v")
        assert result == {}
