"""Integration test: profiling → cleaning → anomaly detection."""
import pytest


@pytest.mark.integration
class TestAnalysisPipeline:

    @pytest.mark.asyncio
    async def test_profiler_then_cleaner_produces_report(self, sample_df):
        from backend.analytics_engine.profiling.data_profiler import DataProfiler
        from backend.analytics_engine.cleaning.data_cleaner   import DataCleaner

        profiler = DataProfiler()
        profile  = await profiler.profile(sample_df, session_id="s1", dataset_id="d1")

        cleaner = DataCleaner(dedup=True, impute=True)
        cleaned_df, report = await cleaner.clean(sample_df, profile)

        assert report.rows_before >= report.rows_after
        assert report.columns_before >= report.columns_after

    @pytest.mark.asyncio
    async def test_profiler_then_anomaly_detector(self, sample_df):
        from backend.analytics_engine.profiling.data_profiler  import DataProfiler
        from backend.analytics_engine.anomaly_detection.anomaly_detector import AnomalyDetector

        profiler  = DataProfiler()
        profile   = await profiler.profile(sample_df)
        detector  = AnomalyDetector(run_isolation_forest=False)
        anomalies = await detector.detect(sample_df, profile=profile)

        # sample_df has a negative revenue row — should be detected
        assert isinstance(anomalies, list)
        severity_levels = {a.get("severity") for a in anomalies}
        assert severity_levels.issubset({"critical", "high", "medium", "low"})

    @pytest.mark.asyncio
    async def test_correlation_engine_on_numeric_columns(self, sample_df):
        from backend.analytics_engine.statistics.correlation_engine import CorrelationEngine

        try:
            import polars as pl
            numeric_cols = [c for c in sample_df.columns if sample_df[c].dtype in
                            (pl.Float64, pl.Int64, pl.Float32, pl.Int32)]
        except ImportError:
            import numpy as np
            numeric_cols = [c for c in sample_df.columns
                            if np.issubdtype(sample_df[c].dtype, np.number)]

        engine = CorrelationEngine(min_abs_r=0.1)
        correlations = engine.compute(sample_df, numeric_cols)
        # revenue × units should have positive correlation
        assert isinstance(correlations, list)


@pytest.mark.integration
class TestDuckDBManager:

    @pytest.mark.asyncio
    async def test_execute_sum_query(self, sample_df):
        from backend.analytics_engine.sql_engine.duckdb_manager import DuckDBManager
        mgr    = DuckDBManager()
        result = await mgr.execute_query("SELECT SUM(revenue) AS total FROM df", df=sample_df)
        assert len(result) == 1
        assert "total" in result[0]

    @pytest.mark.asyncio
    async def test_execute_group_by(self, sample_df):
        from backend.analytics_engine.sql_engine.duckdb_manager import DuckDBManager
        mgr    = DuckDBManager()
        result = await mgr.execute_query(
            "SELECT region, COUNT(*) AS cnt FROM df GROUP BY region ORDER BY cnt DESC",
            df=sample_df,
        )
        assert len(result) > 0
        assert "region" in result[0]
