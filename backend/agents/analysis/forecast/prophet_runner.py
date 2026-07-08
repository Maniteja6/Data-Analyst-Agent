"""Facebook Prophet forecasting runner.

Runs Prophet in a thread-pool executor so it doesn't block the asyncio
event loop during model fitting. Prophet is the preferred model for
business time series because it handles weekly/yearly seasonality and
holiday effects automatically.

Requirements:
    pip install prophet  (wraps cmdstanpy under the hood)
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    import pandas as pd
    import polars as pl

logger = structlog.get_logger(__name__)


async def run_prophet(
    df: pl.DataFrame | pd.DataFrame,
    date_col: str,
    target_col: str,
    horizon: int = 30,
) -> dict[str, Any]:
    """Fit Prophet and forecast ``horizon`` future steps.

    Args:
        df:         Polars or pandas DataFrame with at least date_col and target_col.
        date_col:   Name of the datetime column.
        target_col: Name of the numeric target column.
        horizon:    Number of future periods to forecast.

    Returns:
        Dict with keys: model, predictions (list of timestamp/value/bounds),
        trend_direction, seasonality_mode, error (on failure).
    """
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(
            None, _run_prophet_sync, df, date_col, target_col, horizon
        )
    except Exception as exc:
        logger.warning("prophet_runner_failed", error=str(exc))
        return {"error": str(exc), "model": "Prophet", "predictions": []}


def _run_prophet_sync(
    df: pl.DataFrame | pd.DataFrame, date_col: str, target_col: str, horizon: int
) -> dict[str, Any]:
    """Synchronous Prophet fitting — called in a thread pool executor."""
    try:
        from prophet import Prophet
    except ImportError:
        return {
            "error": "prophet not installed. Run: pip install prophet",
            "model": "Prophet",
            "predictions": [],
        }

    import pandas as pd

    # Convert to pandas with ds/y column names (Prophet requirement)
    try:
        pdf = df.select([date_col, target_col]).drop_nulls().to_pandas()
    except AttributeError:
        pdf = df[[date_col, target_col]].dropna()

    pdf = pdf.rename(columns={date_col: "ds", target_col: "y"})
    pdf["ds"] = pd.to_datetime(pdf["ds"], errors="coerce")
    pdf = pdf.dropna(subset=["ds", "y"]).sort_values("ds").reset_index(drop=True)

    if len(pdf) < 10:
        return {
            "error": f"Insufficient data: {len(pdf)} rows (need ≥ 10)",
            "model": "Prophet",
            "predictions": [],
        }

    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=True,
        daily_seasonality=False,
        interval_width=0.95,
    )

    # Suppress Prophet's verbose logging
    import logging

    logging.getLogger("prophet").setLevel(logging.WARNING)
    logging.getLogger("cmdstanpy").setLevel(logging.WARNING)

    model.fit(pdf)
    future = model.make_future_dataframe(periods=horizon, freq="D")
    forecast = model.predict(future).tail(horizon)

    predictions = [
        {
            "timestamp": str(row["ds"].date()),
            "value": round(float(row["yhat"]), 4),
            "lower_bound": round(float(row["yhat_lower"]), 4),
            "upper_bound": round(float(row["yhat_upper"]), 4),
        }
        for _, row in forecast.iterrows()
    ]

    # Determine trend direction from the last vs first trend value
    trend_series = forecast["trend"].values
    trend_direction = (
        "up"
        if trend_series[-1] > trend_series[0]
        else "down"
        if trend_series[-1] < trend_series[0]
        else "flat"
    )

    logger.info(
        "prophet_complete",
        rows_trained=len(pdf),
        horizon=horizon,
        trend=trend_direction,
    )

    return {
        "model": "Prophet",
        "predictions": predictions,
        "trend_direction": trend_direction,
        "seasonality_mode": "additive",
        "training_rows": len(pdf),
    }
