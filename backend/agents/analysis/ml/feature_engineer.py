"""Feature engineering for the AutoML pipeline.

Prepares a polars or pandas DataFrame for scikit-learn by:
1. Selecting only numeric and categorical columns
2. One-hot encoding low-cardinality categoricals (≤ 10 unique values)
3. Filling nulls with column median (numeric) or mode (categorical)
4. Dropping constant columns (zero variance)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from typing import TypeAlias

    import pandas as pd
    import polars as pl

    DataFrameT: TypeAlias = pl.DataFrame | pd.DataFrame

logger = structlog.get_logger(__name__)


def engineer_features(df: DataFrameT, schema: dict, max_cat_cardinality: int = 10) -> pd.DataFrame:
    """Prepare a feature matrix from the dataset.

    Args:
        df:                  Polars or pandas DataFrame (target column removed).
        schema:              Dataset schema dict with ``columns`` list.
        max_cat_cardinality: Maximum unique values for categorical encoding.

    Returns:
        Pandas DataFrame of numeric features ready for sklearn.
    """
    import numpy as np
    import pandas as pd

    # Convert polars to pandas if needed
    try:
        import polars as pl

        pdf = df.to_pandas() if isinstance(df, pl.DataFrame) else df.copy()
    except ImportError:
        pdf = df.copy()

    col_map = {c["name"]: c.get("semantic_type", "unknown") for c in schema.get("columns", [])}

    numeric_cols = [
        c
        for c in pdf.columns
        if col_map.get(c) in ("currency", "numeric_measure", "numeric_count", "percentage")
        and c in pdf.columns
    ]
    cat_cols = [
        c
        for c in pdf.columns
        if col_map.get(c) == "categorical"
        and c in pdf.columns
        and pdf[c].nunique() <= max_cat_cardinality
    ]

    # Build result frame
    frames = []

    # Numeric: fill with median
    if numeric_cols:
        num_df = pdf[numeric_cols].copy()
        for col in num_df.columns:
            med = num_df[col].median()
            num_df[col] = num_df[col].fillna(med if pd.notna(med) else 0)
        frames.append(num_df)

    # Categorical: one-hot encode
    if cat_cols:
        cat_df = pdf[cat_cols].copy()
        for col in cat_df.columns:
            mode = cat_df[col].mode()
            cat_df[col] = cat_df[col].fillna(mode[0] if len(mode) else "unknown")
        encoded = pd.get_dummies(cat_df, prefix=cat_cols, drop_first=True)
        frames.append(encoded)

    if not frames:
        logger.warning("feature_engineer_no_features", available=list(pdf.columns[:5]))
        # Fallback: use all numeric dtypes
        num_only = pdf.select_dtypes(include=[np.number]).fillna(0)
        return num_only

    result = pd.concat(frames, axis=1)

    # Drop constant columns
    constant_cols = [c for c in result.columns if result[c].nunique() <= 1]
    if constant_cols:
        result = result.drop(columns=constant_cols)
        logger.debug("dropped_constant_columns", count=len(constant_cols))

    logger.info(
        "feature_engineering_complete",
        numeric=len(numeric_cols),
        categorical=len(cat_cols),
        total_features=len(result.columns),
    )
    return result
