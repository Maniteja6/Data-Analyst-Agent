"""DuplicateRemover — removes exact duplicate rows from a DataFrame."""

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


class DuplicateRemover:
    """Removes exact duplicate rows (all columns must match)."""

    def remove(self, df: DataFrameT) -> tuple:
        """Remove duplicate rows and return (cleaned_df, CleaningStep | None)."""
        before = len(df)
        try:
            import polars as pl

            cleaned = df.unique() if isinstance(df, pl.DataFrame) else df.drop_duplicates()
        except Exception:
            cleaned = df.drop_duplicates()

        removed = before - len(cleaned)
        if removed == 0:
            return cleaned, None

        step = CleaningStep(
            action=CleaningAction.REMOVE_DUPLICATES,
            column=None,
            rows_affected=removed,
            description=(
                f"Removed {removed:,} duplicate rows ({removed / before * 100:.1f}% of dataset)."
            ),
        )
        logger.info("duplicates_removed", count=removed, before=before)
        return cleaned, step
