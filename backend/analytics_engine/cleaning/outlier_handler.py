"""OutlierHandler — optional winsorising / clipping of extreme outliers."""

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


class OutlierHandler:
    """Clips extreme outliers beyond the Tukey fence to the fence value."""

    def __init__(self, multiplier: float = 3.0, enabled: bool = False) -> None:
        self._multiplier = multiplier
        self._enabled = enabled

    def handle(self, df: DataFrameT, column: str) -> tuple:
        """Clip extreme outliers and return (df, CleaningStep | None)."""
        if not self._enabled:
            return df, None
        try:
            return self._clip(df, column)
        except Exception as exc:
            logger.debug("outlier_clip_failed", column=column, error=str(exc))
            return df, None

    def _clip(self, df: DataFrameT, column: str) -> tuple:
        try:
            import polars as pl

            is_polars = isinstance(df, pl.DataFrame)
        except ImportError:
            is_polars = False

        if is_polars:
            series = df[column].drop_nulls()
            q1 = float(series.quantile(0.25))
            q3 = float(series.quantile(0.75))
            iqr = q3 - q1
            lower, upper = q1 - self._multiplier * iqr, q3 + self._multiplier * iqr
            clipped = df.with_columns(df[column].clip(lower, upper).alias(column))
            affected = int((df[column].drop_nulls() < lower).sum()) + int(
                (df[column].drop_nulls() > upper).sum()
            )
        else:
            series = df[column].dropna()
            q1, q3 = series.quantile(0.25), series.quantile(0.75)
            iqr = q3 - q1
            lower, upper = q1 - self._multiplier * iqr, q3 + self._multiplier * iqr
            affected = int(((df[column] < lower) | (df[column] > upper)).sum())
            clipped = df.copy()
            clipped[column] = df[column].clip(lower=lower, upper=upper)

        if affected == 0:
            return df, None

        step = CleaningStep(
            action=CleaningAction.CLIP_OUTLIER,
            column=column,
            rows_affected=affected,
            description=(
                f"Clipped {affected:,} extreme outliers in '{column}' "
                f"to [{lower:.4g}, {upper:.4g}]."
            ),
        )
        return clipped, step
