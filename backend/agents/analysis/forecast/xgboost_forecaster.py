"""XGBoost-based time series forecaster using lag features.

Used as a fallback when Prophet and ARIMA are unavailable, and as a
complementary model for datasets with many correlated exogenous features.

Feature engineering:
    Lag features at 1, 7, 14, 21 days create a sliding window that
    captures short-term momentum and weekly seasonality.
    An autoregressive rollout generates predictions one step at a time
    so each step's prediction becomes an input to the next step.

Requirements:
    pip install xgboost
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

LAG_DAYS = [1, 7, 14, 21]


async def run_xgboost(
    df,
    date_col: str,
    target_col: str,
    horizon: int = 30,
) -> dict[str, Any]:
    """Fit XGBoost with lag features and forecast ``horizon`` future steps.

    Args:
        df:         Polars or pandas DataFrame.
        date_col:   Name of the datetime column (used for sorting only).
        target_col: Name of the numeric target column.
        horizon:    Number of future periods to forecast.

    Returns:
        Dict with keys: model, predictions, feature_importances, error.
    """
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(
            None, _run_xgboost_sync, df, date_col, target_col, horizon
        )
    except Exception as exc:
        logger.warning("xgboost_forecaster_failed", error=str(exc))
        return {"error": str(exc), "model": "XGBoost", "predictions": []}


def _run_xgboost_sync(
    df, date_col: str, target_col: str, horizon: int
) -> dict:
    """Synchronous XGBoost fitting — called in a thread pool executor."""
    try:
        from xgboost import XGBRegressor
    except ImportError:
        return {
            "error": "xgboost not installed. Run: pip install xgboost",
            "model": "XGBoost",
            "predictions": [],
        }

    import pandas as pd
    import numpy as np

    # Convert to pandas and sort by date
    try:
        pdf = df.select([date_col, target_col]).drop_nulls().to_pandas()
    except AttributeError:
        pdf = df[[date_col, target_col]].dropna()

    pdf = pdf.rename(columns={date_col: "ds", target_col: "y"})
    pdf["ds"] = pd.to_datetime(pdf["ds"], errors="coerce")
    pdf = pdf.dropna(subset=["ds", "y"]).sort_values("ds").reset_index(drop=True)

    if len(pdf) < max(LAG_DAYS) + 5:
        return {
            "error": f"Insufficient data: {len(pdf)} rows (need ≥ {max(LAG_DAYS) + 5})",
            "model": "XGBoost",
            "predictions": [],
        }

    # Build lag features
    for lag in LAG_DAYS:
        pdf[f"lag_{lag}"] = pdf["y"].shift(lag)

    # Date-based features for seasonality
    pdf["day_of_week"] = pdf["ds"].dt.dayofweek
    pdf["month"]       = pdf["ds"].dt.month

    pdf = pdf.dropna().reset_index(drop=True)
    feature_cols = [f"lag_{l}" for l in LAG_DAYS] + ["day_of_week", "month"]

    model = XGBRegressor(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        random_state=42,
        n_jobs=-1,
        verbosity=0,
    )
    model.fit(pdf[feature_cols], pdf["y"])

    importances = dict(zip(feature_cols, model.feature_importances_.tolist()))

    # Autoregressive rollout
    last_values = list(pdf["y"].values)
    last_date   = pdf["ds"].iloc[-1]
    predictions = []

    for step in range(horizon):
        next_date  = last_date + pd.Timedelta(days=step + 1)
        row = {
            f"lag_{l}": last_values[-(l)] if l <= len(last_values) else 0
            for l in LAG_DAYS
        }
        row["day_of_week"] = next_date.dayofweek
        row["month"]       = next_date.month

        pred = float(model.predict(pd.DataFrame([row]))[0])
        predictions.append({
            "timestamp":   str(next_date.date()),
            "value":       round(pred, 4),
            "lower_bound": round(pred * 0.90, 4),
            "upper_bound": round(pred * 1.10, 4),
        })
        last_values.append(pred)

    logger.info(
        "xgboost_complete",
        rows_trained=len(pdf),
        horizon=horizon,
        top_feature=max(importances, key=importances.get),
    )

    return {
        "model":               "XGBoost",
        "predictions":         predictions,
        "feature_importances": importances,
        "training_rows":       len(pdf),
    }
