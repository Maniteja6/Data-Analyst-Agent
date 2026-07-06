"""Data cleaning — duplicate removal, imputation, type coercion, outlier handling."""
"""Cleaning — deterministic data cleaning pipeline.

DataCleaner:         async clean(df, profile) → (cleaned_df, CleaningReport).
                     Runs: whitespace strip → dedup → type coerce → impute → clip.
DuplicateRemover:    polars unique() / pandas drop_duplicates().
MissingValueHandler: drop cols ≥ 80% null; numeric=median impute; text=mode impute.
TypeCoercer:         string→float (strips $€£%) and string→datetime (dateutil).
OutlierHandler:      optional Tukey fence clipping; disabled by default.
"""
from backend.analytics_engine.cleaning.data_cleaner import DataCleaner

__all__ = ["DataCleaner"]
