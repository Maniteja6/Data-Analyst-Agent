"""MissingValueHandler — imputes or drops columns with excessive nulls."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from backend.domain.analytics.entities.cleaning_report import CleaningAction, CleaningStep

if TYPE_CHECKING:
    from typing import TypeAlias

    import pandas as pd
    import polars as pl

    DataFrameT: TypeAlias = pl.DataFrame | pd.DataFrame

logger = structlog.get_logger(__name__)

# Columns with more than 80% nulls are dropped rather than imputed
HIGH_NULL_THRESHOLD = 0.80


class MissingValueHandler:
    """Handles missing values via imputation or column dropping."""

    def __init__(self, high_null_threshold: float = HIGH_NULL_THRESHOLD) -> None:
        self._threshold = high_null_threshold

    def handle(self, df: DataFrameT, column_profiles: list) -> tuple:
        """Impute or drop columns based on null rate.

        Returns (cleaned_df, list[CleaningStep]).
        """
        steps: list[CleaningStep] = []
        try:
            import polars as pl

            is_polars = isinstance(df, pl.DataFrame)
        except ImportError:
            is_polars = False

        for cp in column_profiles:
            col = cp.column_name if hasattr(cp, "column_name") else cp.get("column_name", "")
            null_rate = cp.null_rate if hasattr(cp, "null_rate") else cp.get("null_rate", 0.0)
            kind = str(
                cp.kind.value
                if hasattr(cp.kind, "value")
                else cp.kind
                if hasattr(cp, "kind")
                else "unknown"
            )

            if col not in (df.columns if is_polars else df.columns.tolist()):
                continue

            if null_rate >= self._threshold:
                df, step = self._drop_column(df, col, is_polars, null_rate)
                steps.append(step)
            elif null_rate > 0:
                df, step = self._impute(df, col, kind, is_polars)
                if step:
                    steps.append(step)

        return df, steps

    def _drop_column(self, df: DataFrameT, col: str, is_polars: bool, null_rate: float) -> tuple:
        df = df.drop(col) if is_polars else df.drop(columns=[col])
        step = CleaningStep(
            action=CleaningAction.DROP_HIGH_NULL_COL,
            column=col,
            rows_affected=0,
            description=(
                f"Dropped column '{col}' ({null_rate * 100:.0f}% nulls — exceeds threshold)."
            ),
        )
        logger.info("column_dropped_high_null", column=col, null_rate=null_rate)
        return df, step

    def _impute(self, df: DataFrameT, col: str, kind: str, is_polars: bool) -> tuple:
        if kind == "numeric":
            action = CleaningAction.IMPUTE_MEDIAN
            if is_polars:
                median = df[col].median()
                df = df.with_columns(df[col].fill_null(median).alias(col))
            else:
                df[col] = df[col].fillna(df[col].median())
            desc = f"Imputed missing values in '{col}' with column median."
        elif kind == "text":
            action = CleaningAction.IMPUTE_MODE
            if is_polars:
                mode = df[col].drop_nulls().mode()[0] if len(df[col].drop_nulls()) > 0 else ""
                df = df.with_columns(df[col].fill_null(mode).alias(col))
            else:
                mode = df[col].mode()[0] if len(df[col].dropna()) > 0 else ""
                df[col] = df[col].fillna(mode)
            desc = f"Imputed missing values in '{col}' with column mode."
        else:
            return df, None

        int(getattr(df[col], "null_count", lambda: 0)() if is_polars else df[col].isna().sum())
        step = CleaningStep(action=action, column=col, rows_affected=0, description=desc)
        return df, step
