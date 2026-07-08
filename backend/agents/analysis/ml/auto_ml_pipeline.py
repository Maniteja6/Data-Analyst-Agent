"""Simple AutoML pipeline using scikit-learn.

Automatically determines whether the task is classification or regression
based on the number of unique target values, then runs a Random Forest
with 3-fold cross-validation.

For regression:  scoring = R²
For classification: scoring = accuracy
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from typing import TypeAlias

    import pandas as pd
    import polars as pl

    DataFrameT: TypeAlias = pl.DataFrame | pd.DataFrame

logger = structlog.get_logger(__name__)

N_ESTIMATORS = 100
CV_FOLDS = 3
MAX_TRAIN_ROWS = 50_000


async def run_automl(
    df: DataFrameT,
    target_col: str,
    schema: dict,
) -> dict[str, Any]:
    """Run AutoML on the dataset.

    Args:
        df:         Polars or pandas DataFrame (full dataset).
        target_col: Column to predict.
        schema:     Dataset schema dict (passed to feature_engineer).

    Returns:
        Dict with keys: task, target, features, cv_score_mean, cv_score_std,
        scoring, feature_importances, model_type, error (on failure).
    """
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _run_automl_sync, df, target_col, schema)
    except Exception as exc:
        logger.warning("automl_failed", error=str(exc))
        return {"error": str(exc)}


def _run_automl_sync(df: DataFrameT, target_col: str, schema: dict) -> dict:
    """Synchronous AutoML — runs in thread pool."""
    try:
        import numpy as np
        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
        from sklearn.model_selection import cross_val_score
    except ImportError:
        return {"error": "scikit-learn not installed. Run: pip install scikit-learn"}

    from backend.agents.analysis.ml.feature_engineer import engineer_features

    # Convert to pandas
    try:
        import polars as pl

        pdf = df.to_pandas() if isinstance(df, pl.DataFrame) else df.copy()
    except ImportError:
        pdf = df.copy()

    if target_col not in pdf.columns:
        return {"error": f"Target column '{target_col}' not found in dataset"}

    # Sample for performance
    if len(pdf) > MAX_TRAIN_ROWS:
        pdf = pdf.sample(n=MAX_TRAIN_ROWS, random_state=42)

    y = pdf[target_col].fillna(0).to_numpy()

    # Build feature matrix (drop target from schema context)
    feature_df = engineer_features(pdf.drop(columns=[target_col]), schema)
    if feature_df.empty or len(feature_df.columns) == 0:
        return {"error": "No usable features could be engineered from this dataset"}

    x_data = feature_df.to_numpy()

    # Auto-detect task type
    n_unique = len(np.unique(y))
    if n_unique <= 20 and y.dtype.kind in ("i", "u", "S", "U", "O"):
        model = RandomForestClassifier(n_estimators=N_ESTIMATORS, random_state=42, n_jobs=-1)
        task = "classification"
        scoring = "accuracy"
    else:
        model = RandomForestRegressor(n_estimators=N_ESTIMATORS, random_state=42, n_jobs=-1)
        task = "regression"
        scoring = "r2"

    try:
        scores = cross_val_score(model, x_data, y, cv=CV_FOLDS, scoring=scoring)
        model.fit(x_data, y)
        importances = dict(
            zip(
                feature_df.columns,
                model.feature_importances_.tolist(),
                strict=False,
            )
        )
        top_features = dict(sorted(importances.items(), key=lambda x: -x[1])[:10])
    except Exception as exc:
        return {"error": f"Model training failed: {exc}"}

    logger.info(
        "automl_complete",
        task=task,
        target=target_col,
        cv_score=round(float(scores.mean()), 4),
        features=len(feature_df.columns),
    )

    return {
        "task": task,
        "target": target_col,
        "model_type": "RandomForest",
        "features": list(feature_df.columns),
        "feature_count": len(feature_df.columns),
        "cv_score_mean": round(float(scores.mean()), 4),
        "cv_score_std": round(float(scores.std()), 4),
        "scoring": scoring,
        "feature_importances": top_features,
        "training_rows": len(pdf),
    }
