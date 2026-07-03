"""DataCleaner — orchestrates all cleaning steps and produces a CleaningReport."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import structlog

from backend.analytics_engine.cleaning.duplicate_remover      import DuplicateRemover
from backend.analytics_engine.cleaning.missing_value_handler  import MissingValueHandler
from backend.analytics_engine.cleaning.type_coercer           import TypeCoercer
from backend.analytics_engine.cleaning.outlier_handler        import OutlierHandler
from backend.domain.analytics.entities.cleaning_report        import CleaningReport
from backend.shared.utils.uuid_factory import new_uuid

logger = structlog.get_logger(__name__)


class DataCleaner:
    """Applies duplicate removal, null imputation, type coercion, and outlier clipping."""

    def __init__(
        self,
        dedup: bool = True,
        impute: bool = True,
        coerce_types: bool = True,
        clip_outliers: bool = False,
    ) -> None:
        self._dedup_enabled   = dedup
        self._impute_enabled  = impute
        self._coerce_enabled  = coerce_types
        self._clip_enabled    = clip_outliers
        self._dedup_r   = DuplicateRemover()
        self._missing   = MissingValueHandler()
        self._coercer   = TypeCoercer()
        self._outlier   = OutlierHandler(enabled=clip_outliers)

    async def clean(
        self,
        df,
        profile,
        session_id: str = "",
        dataset_id: str = "",
    ) -> tuple:
        """Clean a DataFrame and return (cleaned_df, CleaningReport).

        Args:
            df:         Raw DataFrame from FileReader.
            profile:    DataProfile from DataProfiler (provides column metadata).
            session_id: AnalysisSession identifier.
            dataset_id: Source Dataset identifier.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._clean_sync(df, profile, session_id, dataset_id),
        )

    def _clean_sync(self, df, profile, session_id: str, dataset_id: str) -> tuple:
        all_steps = []
        rows_before   = len(df)
        cols_before   = len(df.columns) if hasattr(df, "columns") else 0

        col_profiles = getattr(profile, "column_profiles", [])

        # Step 1: Whitespace stripping (text columns)
        df = self._strip_whitespace(df, col_profiles)

        # Step 2: Remove duplicates
        if self._dedup_enabled:
            df, step = self._dedup_r.remove(df)
            if step:
                all_steps.append(step)

        # Step 3: Type coercion (string → float/datetime)
        if self._coerce_enabled:
            df, steps = self._coercer.coerce(df, col_profiles)
            all_steps.extend(steps)

        # Step 4: Missing value imputation / column dropping
        if self._impute_enabled:
            df, steps = self._missing.handle(df, col_profiles)
            all_steps.extend(steps)

        # Step 5: Optional outlier clipping
        if self._clip_enabled:
            for cp in col_profiles:
                col  = cp.column_name if hasattr(cp, "column_name") else ""
                kind = str(getattr(getattr(cp, "kind", None), "value", getattr(cp, "kind", "unknown")))
                if kind == "numeric" and col in (df.columns if hasattr(df.columns, "__iter__") else []):
                    df, step = self._outlier.handle(df, col)
                    if step:
                        all_steps.append(step)

        report = CleaningReport(
            id=new_uuid(),
            session_id=session_id,
            dataset_id=dataset_id,
            rows_before=rows_before,
            rows_after=len(df),
            columns_before=cols_before,
            columns_after=len(df.columns) if hasattr(df, "columns") else 0,
            steps=all_steps,
            cleaned_at=datetime.now(timezone.utc),
        )

        logger.info(
            "cleaning_complete",
            rows_removed=report.rows_removed,
            columns_removed=report.columns_removed,
            steps=len(all_steps),
        )
        return df, report

    @staticmethod
    def _strip_whitespace(df, col_profiles: list):
        """Strip leading/trailing whitespace from string columns."""
        try:
            import polars as pl
            if isinstance(df, pl.DataFrame):
                str_cols = [
                    cp.column_name for cp in col_profiles
                    if hasattr(cp, "kind") and str(getattr(cp.kind, "value", cp.kind)) == "text"
                    and cp.column_name in df.columns
                ]
                if str_cols:
                    df = df.with_columns([pl.col(c).str.strip_chars().alias(c) for c in str_cols])
                return df
        except Exception:
            pass
        try:
            str_cols = df.select_dtypes(include="object").columns.tolist()
            for c in str_cols:
                df[c] = df[c].str.strip()
        except Exception:
            pass
        return df
