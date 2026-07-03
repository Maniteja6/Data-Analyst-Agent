"""TypeCoercer — coerces string columns to their inferred semantic types."""
from __future__ import annotations

import structlog
from backend.domain.analytics.entities.cleaning_report import CleaningStep, CleaningAction

logger = structlog.get_logger(__name__)


class TypeCoercer:
    """Coerces string columns to numeric or datetime where appropriate."""

    def coerce(self, df, column_profiles: list) -> tuple:
        """Apply type coercions based on semantic_type from the profile.

        Returns (cleaned_df, list[CleaningStep]).
        """
        steps: list[CleaningStep] = []
        try:
            import polars as pl
            is_polars = isinstance(df, pl.DataFrame)
        except ImportError:
            is_polars = False

        for cp in column_profiles:
            col   = cp.column_name if hasattr(cp, "column_name") else cp.get("column_name", "")
            stype = str(cp.semantic_type.value if hasattr(getattr(cp, "semantic_type", None), "value")
                        else getattr(cp, "semantic_type", "unknown"))
            dtype = str(cp.data_type if hasattr(cp, "data_type") else cp.get("data_type", ""))

            if "Utf8" not in dtype and "object" not in dtype and "str" not in dtype.lower():
                continue

            if stype in ("currency", "numeric_measure", "numeric_count", "percentage"):
                df, step = self._coerce_to_float(df, col, is_polars)
                if step:
                    steps.append(step)
            elif stype in ("date", "datetime"):
                df, step = self._coerce_to_datetime(df, col, is_polars)
                if step:
                    steps.append(step)

        return df, steps

    def _coerce_to_float(self, df, col: str, is_polars: bool) -> tuple:
        try:
            if is_polars:
                df = df.with_columns(
                    df[col]
                    .str.replace_all(r"[,$€£%]", "")
                    .str.strip_chars()
                    .cast(float, strict=False)
                    .alias(col)
                )
            else:
                df[col] = df[col].replace(r"[,$€£%]", "", regex=True).str.strip()
                df[col] = df[col].apply(lambda x: float(x) if x else None, errors="coerce" if hasattr(df[col], "astype") else None)
            step = CleaningStep(
                action=CleaningAction.COERCE_TO_FLOAT,
                column=col,
                rows_affected=0,
                description=f"Coerced '{col}' from string to float (removed currency symbols).",
            )
            return df, step
        except Exception as exc:
            logger.debug("type_coerce_float_failed", column=col, error=str(exc))
            return df, None

    def _coerce_to_datetime(self, df, col: str, is_polars: bool) -> tuple:
        try:
            if is_polars:
                import polars as pl
                df = df.with_columns(pl.col(col).str.to_datetime(strict=False).alias(col))
            else:
                import pandas as pd
                df[col] = pd.to_datetime(df[col], errors="coerce")
            step = CleaningStep(
                action=CleaningAction.COERCE_TO_DATETIME,
                column=col,
                rows_affected=0,
                description=f"Coerced '{col}' from string to datetime.",
            )
            return df, step
        except Exception as exc:
            logger.debug("type_coerce_datetime_failed", column=col, error=str(exc))
            return df, None
