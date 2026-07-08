"""Unit tests for DataProfiler."""

import pytest


@pytest.mark.unit
class TestDataProfiler:
    @pytest.mark.asyncio
    async def test_profile_returns_data_profile(self, sample_df) -> None:
        from backend.analytics_engine.profiling.data_profiler import DataProfiler

        profiler = DataProfiler()
        profile = await profiler.profile(sample_df, session_id="s1", dataset_id="d1")
        assert profile.row_count > 0
        assert profile.column_count > 0
        assert len(profile.column_profiles) == profile.column_count

    @pytest.mark.asyncio
    async def test_numeric_columns_have_stats(self, sample_df) -> None:
        from backend.analytics_engine.profiling.data_profiler import DataProfiler
        from backend.domain.analytics.entities.column_profile import ColumnKind

        profiler = DataProfiler()
        profile = await profiler.profile(sample_df)
        numeric = [cp for cp in profile.column_profiles if cp.kind == ColumnKind.NUMERIC]
        assert len(numeric) > 0
        for col in numeric:
            assert col.stats is not None
            assert col.stats.count > 0

    @pytest.mark.asyncio
    async def test_completeness_is_one_for_clean_data(self, sample_df) -> None:
        from backend.analytics_engine.profiling.data_profiler import DataProfiler

        profiler = DataProfiler()
        profile = await profiler.profile(sample_df)
        # sample_df has no nulls in most columns
        assert profile.completeness_score >= 0.85

    @pytest.mark.asyncio
    async def test_duplicate_count_zero_for_unique_data(self, sample_df) -> None:
        from backend.analytics_engine.profiling.data_profiler import DataProfiler

        profiler = DataProfiler()
        profile = await profiler.profile(sample_df)
        assert profile.duplicate_count == 0

    @pytest.mark.asyncio
    async def test_profile_handles_all_nulls_column(self) -> None:
        """Profiler must not crash on an all-null column."""
        try:
            import polars as pl

            df = pl.DataFrame({"a": [1, 2, 3], "b": [None, None, None]})
        except ImportError:
            import pandas as pd

            df = pd.DataFrame({"a": [1, 2, 3], "b": [None, None, None]})

        from backend.analytics_engine.profiling.data_profiler import DataProfiler

        profiler = DataProfiler()
        profile = await profiler.profile(df)
        assert profile.column_count == 2
