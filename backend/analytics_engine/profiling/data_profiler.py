"""DataProfiler — orchestrates per-column profiling and produces a DataProfile."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog

from backend.analytics_engine.profiling.numeric_profiler     import NumericProfiler
from backend.analytics_engine.profiling.categorical_profiler import CategoricalProfiler
from backend.analytics_engine.profiling.datetime_profiler    import DatetimeProfiler
from backend.analytics_engine.profiling.text_profiler        import TextProfiler
from backend.domain.analytics.entities.analysis_session      import AnalysisSession
from backend.domain.analytics.entities.data_profile          import DataProfile
from backend.domain.analytics.entities.column_profile        import ColumnProfile, ColumnKind
from backend.shared.utils.uuid_factory import new_uuid

logger = structlog.get_logger(__name__)


class DataProfiler:
    """Builds a DataProfile from a DataFrame by running per-column profilers."""

    def __init__(
        self,
        sample_size: int = 100_000,
        top_n_values: int = 20,
    ) -> None:
        self._numeric      = NumericProfiler(sample_size=sample_size)
        self._categorical  = CategoricalProfiler(top_n=top_n_values)
        self._datetime_p   = DatetimeProfiler()
        self._text         = TextProfiler()

    async def profile(self, df, session_id: str = "", dataset_id: str = "") -> DataProfile:
        """Run all column profilers and return a DataProfile entity.

        Profiling is offloaded to a thread-pool executor so it doesn't
        block the event loop.
        """
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: self._profile_sync(df, session_id, dataset_id))
        return result

    def _profile_sync(self, df, session_id: str, dataset_id: str) -> DataProfile:
        """Synchronous profiling implementation run in a thread."""
        column_profiles: list[ColumnProfile] = []

        try:
            import polars as pl
            is_polars = isinstance(df, pl.DataFrame)
        except ImportError:
            is_polars = False

        row_count     = len(df)
        col_count     = len(df.columns) if is_polars else len(df.columns)
        duplicate_count = self._count_duplicates(df, is_polars)

        for col in df.columns:
            try:
                col_profile = self._profile_column(df, col, row_count, is_polars)
                column_profiles.append(col_profile)
            except Exception as exc:
                logger.warning("column_profile_failed", column=col, error=str(exc))

        # Compute dataset-level completeness
        total_cells    = row_count * col_count
        null_cells     = sum(cp.null_count for cp in column_profiles)
        completeness   = round(1 - (null_cells / total_cells), 6) if total_cells > 0 else 1.0
        consistency    = round(1 - (duplicate_count / row_count), 6) if row_count > 0 else 1.0

        profile = DataProfile(
            id=new_uuid(),
            session_id=session_id,
            dataset_id=dataset_id,
            row_count=row_count,
            column_count=col_count,
            duplicate_count=duplicate_count,
            completeness_score=completeness,
            consistency_score=consistency,
            column_profiles=column_profiles,
            profiled_at=datetime.now(timezone.utc),
        )
        logger.info(
            "profiling_complete",
            rows=row_count,
            cols=col_count,
            completeness=completeness,
            columns_profiled=len(column_profiles),
        )
        return profile

    def _profile_column(self, df, column: str, total_rows: int, is_polars: bool) -> ColumnProfile:
        """Profile one column and return a ColumnProfile entity."""
        kind, data_type = self._detect_kind(df, column, is_polars)

        null_count   = self._null_count(df, column, is_polars)
        unique_count = self._unique_count(df, column, is_polars)
        sample_vals  = self._sample_values(df, column, is_polars)

        cp = ColumnProfile(
            id=new_uuid(),
            session_id="",
            column_name=column,
            data_type=data_type,
            kind=kind,
            total_rows=total_rows,
            null_count=null_count,
            unique_count=unique_count,
            sample_values=sample_vals,
        )

        if kind == ColumnKind.NUMERIC:
            stats, histogram = self._numeric.profile(df, column)
            cp.stats         = stats
            cp.histogram     = histogram

        elif kind == ColumnKind.TEXT:
            top_values, histogram = self._categorical.profile(df, column)
            cp.top_values = top_values
            cp.histogram  = histogram

        elif kind == ColumnKind.DATETIME:
            _ = self._datetime_p.profile(df, column)

        return cp

    # ── Detection helpers ─────────────────────────────────────────────────

    @staticmethod
    def _detect_kind(df, column: str, is_polars: bool) -> tuple[ColumnKind, str]:
        """Return (ColumnKind, dtype_string) for a column."""
        try:
            if is_polars:
                import polars as pl
                dtype = df[column].dtype
                dtype_str = str(dtype)
                if dtype in (pl.Float32, pl.Float64, pl.Int8, pl.Int16, pl.Int32, pl.Int64,
                             pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64):
                    return ColumnKind.NUMERIC, dtype_str
                if dtype in (pl.Date, pl.Datetime, pl.Time, pl.Duration):
                    return ColumnKind.DATETIME, dtype_str
                if dtype == pl.Boolean:
                    return ColumnKind.BOOLEAN, dtype_str
                return ColumnKind.TEXT, dtype_str
            else:
                import numpy as np
                dtype = df[column].dtype
                if np.issubdtype(dtype, np.number):
                    return ColumnKind.NUMERIC, str(dtype)
                if np.issubdtype(dtype, np.datetime64) or str(dtype).startswith("datetime"):
                    return ColumnKind.DATETIME, str(dtype)
                if str(dtype) == "bool":
                    return ColumnKind.BOOLEAN, str(dtype)
                return ColumnKind.TEXT, str(dtype)
        except Exception:
            return ColumnKind.UNKNOWN, "unknown"

    @staticmethod
    def _null_count(df, column: str, is_polars: bool) -> int:
        try:
            if is_polars:
                return int(df[column].null_count())
            return int(df[column].isna().sum())
        except Exception:
            return 0

    @staticmethod
    def _unique_count(df, column: str, is_polars: bool) -> int:
        try:
            if is_polars:
                return int(df[column].drop_nulls().n_unique())
            return int(df[column].nunique())
        except Exception:
            return 0

    @staticmethod
    def _sample_values(df, column: str, is_polars: bool, n: int = 5) -> list[str]:
        try:
            if is_polars:
                vals = df[column].drop_nulls().head(n).to_list()
            else:
                vals = df[column].dropna().head(n).tolist()
            return [str(v) for v in vals]
        except Exception:
            return []

    @staticmethod
    def _count_duplicates(df, is_polars: bool) -> int:
        try:
            if is_polars:
                return len(df) - len(df.unique())
            return int(df.duplicated().sum())
        except Exception:
            return 0
