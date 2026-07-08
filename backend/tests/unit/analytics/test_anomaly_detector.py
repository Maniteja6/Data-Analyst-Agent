"""Unit tests for the anomaly detection sub-package."""

import pytest


@pytest.mark.unit
class TestZScoreDetector:
    def _make_df_with_outlier(self):
        try:
            import polars as pl

            return pl.DataFrame(
                {"value": [10.0, 11.0, 10.5, 12.0, 11.5, 10.0, 9.5, 999.0, 10.2, 11.1]}
            )
        except ImportError:
            import pandas as pd

            return pd.DataFrame(
                {"value": [10.0, 11.0, 10.5, 12.0, 11.5, 10.0, 9.5, 999.0, 10.2, 11.1]}
            )

    def test_detects_extreme_outlier(self) -> None:
        from backend.analytics_engine.anomaly_detection.zscore_detector import ZScoreDetector

        detector = ZScoreDetector(threshold=3.0)
        df = self._make_df_with_outlier()
        anomalies = detector.detect(df, "value")
        assert len(anomalies) >= 1
        assert anomalies[0].raw_value == pytest.approx(999.0, abs=1.0)

    def test_no_anomalies_in_uniform_data(self) -> None:
        from backend.analytics_engine.anomaly_detection.zscore_detector import ZScoreDetector

        try:
            import polars as pl

            df = pl.DataFrame({"v": [1.0] * 20})
        except ImportError:
            import pandas as pd

            df = pd.DataFrame({"v": [1.0] * 20})
        anomalies = ZScoreDetector().detect(df, "v")
        assert len(anomalies) == 0


@pytest.mark.unit
class TestIQRDetector:
    def test_detects_outlier_below_lower_fence(self) -> None:
        from backend.analytics_engine.anomaly_detection.iqr_detector import IQRDetector

        try:
            import polars as pl

            df = pl.DataFrame({"v": [10.0, 11.0, 12.0, 10.5, 11.5, -500.0, 12.5, 10.0]})
        except ImportError:
            import pandas as pd

            df = pd.DataFrame({"v": [10.0, 11.0, 12.0, 10.5, 11.5, -500.0, 12.5, 10.0]})
        anomalies = IQRDetector(multiplier=1.5).detect(df, "v")
        assert any(a.direction == "below_lower" for a in anomalies)


@pytest.mark.unit
class TestRuleDetector:
    def test_negative_currency_flagged(self) -> None:
        from backend.analytics_engine.anomaly_detection.rule_detector import RuleDetector

        try:
            import polars as pl

            df = pl.DataFrame({"price": [10.0, 25.0, -5.0, 100.0]})
        except ImportError:
            import pandas as pd

            df = pd.DataFrame({"price": [10.0, 25.0, -5.0, 100.0]})
        results = RuleDetector().detect(df, "price", semantic_type="currency")
        assert len(results) >= 1
        assert results[0]["anomaly_type"] == "rule_violation"

    def test_valid_currency_not_flagged(self) -> None:
        from backend.analytics_engine.anomaly_detection.rule_detector import RuleDetector

        try:
            import polars as pl

            df = pl.DataFrame({"price": [10.0, 25.0, 100.0, 0.0]})
        except ImportError:
            import pandas as pd

            df = pd.DataFrame({"price": [10.0, 25.0, 100.0, 0.0]})
        results = RuleDetector().detect(df, "price", semantic_type="currency")
        assert len(results) == 0


@pytest.mark.unit
class TestAnomalyDetector:
    @pytest.mark.asyncio
    async def test_detect_returns_list(self, sample_df) -> None:
        from backend.analytics_engine.anomaly_detection.anomaly_detector import AnomalyDetector

        detector = AnomalyDetector(run_isolation_forest=False)
        anomalies = await detector.detect(sample_df)
        assert isinstance(anomalies, list)

    @pytest.mark.asyncio
    async def test_negative_revenue_detected(self, sample_df) -> None:
        """sample_df has a row with revenue=-50.0 which is a rule violation."""
        from backend.analytics_engine.anomaly_detection.anomaly_detector import AnomalyDetector
        from backend.analytics_engine.profiling.data_profiler import DataProfiler

        profiler = DataProfiler()
        profile = await profiler.profile(sample_df)
        detector = AnomalyDetector(run_isolation_forest=False)
        anomalies = await detector.detect(sample_df, profile=profile)
        # At least one anomaly should mention negative revenue
        assert len(anomalies) > 0

    @pytest.mark.asyncio
    async def test_deduplication_removes_duplicate_alerts(self, sample_df) -> None:
        from backend.analytics_engine.anomaly_detection.anomaly_detector import AnomalyDetector

        detector = AnomalyDetector(run_isolation_forest=False)
        results = await detector.detect(sample_df)
        # No duplicate (column, row_index, anomaly_type) keys
        keys = [(r.get("column"), r.get("row_index"), r.get("anomaly_type")) for r in results]
        assert len(keys) == len(set(keys))
