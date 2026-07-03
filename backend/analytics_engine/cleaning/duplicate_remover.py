"""DuplicateRemover — removes exact duplicate rows from a DataFrame."""
from __future__ import annotations

import structlog
from backend.domain.analytics.entities.cleaning_report import CleaningStep, CleaningAction

logger = structlog.get_logger(__name__)


class DuplicateRemover:
    """Removes exact duplicate rows (all columns must match)."""

    def remove(self, df) -> tuple:
        """Remove duplicate rows and return (cleaned_df, CleaningStep | None)."""
        before = len(df)
        try:
            import polars as pl
            if isinstance(df, pl.DataFrame):
                cleaned = df.unique()
            else:
                cleaned = df.drop_duplicates()
        except Exception:
            cleaned = df.drop_duplicates()

        removed = before - len(cleaned)
        if removed == 0:
            return cleaned, None

        step = CleaningStep(
            action=CleaningAction.REMOVE_DUPLICATES,
            column=None,
            rows_affected=removed,
            description=f"Removed {removed:,} duplicate rows ({removed/before*100:.1f}% of dataset).",
        )
        logger.info("duplicates_removed", count=removed, before=before)
        return cleaned, step
