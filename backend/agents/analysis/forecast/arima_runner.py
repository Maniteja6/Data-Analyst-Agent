"""AutoARIMA forecasting runner via statsforecast.

Uses Nixtla's statsforecast library which provides a fast, vectorised
AutoARIMA implementation that auto-selects p/d/q parameters via AIC.

Requirements:
    pip install statsforecast
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def run_arima(
    df: Any,
    date_col: str,
    target_col: str,
    horizon: int = 30,
    season_length: int = 7,
) -> dict[str, Any]:
    """Fit AutoARIMA and forecast ``horizon`` future steps.

    Args:
        df:            Polars or pandas DataFrame.
        date_col:      Name of the datetime column.
        target_col:    Name of the numeric target column.
        horizon:       Number of future periods to forecast.
        season_length: Seasonal period (7 = weekly, 12 = monthly).

    Returns:
        Dict with keys: model, predictions, error (on failure).
    """
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(
            None, _run_arima_sync, df, date_col, target_col, horizon, season_length
        )
    except Exception as exc:
        logger.warning("arima_runner_failed", error=str(exc))
        return {"error": str(exc), "model": "AutoARIMA", "predictions": []}


def _run_arima_sync(
    df: Any, date_col: str, target_col: str, horizon: int, season_length: int
) -> dict[str, Any]:
    """Synchronous ARIMA fitting — called in a thread pool executor."""
    try:
        from statsforecast import StatsForecast
        from statsforecast.models import AutoARIMA
    except ImportError:
        return {
            "error": "statsforecast not installed. Run: pip install statsforecast",
            "model": "AutoARIMA",
            "predictions": [],
        }

    import pandas as pd

    # Convert to pandas
    try:
        pdf = df.select([date_col, target_col]).drop_nulls().to_pandas()
    except AttributeError:
        pdf = df[[date_col, target_col]].dropna()

    pdf = pdf.rename(columns={date_col: "ds", target_col: "y"})
    pdf["ds"]        = pd.to_datetime(pdf["ds"], errors="coerce")
    pdf["unique_id"] = "series_1"
    pdf = pdf.dropna(subset=["ds", "y"]).sort_values("ds").reset_index(drop=True)

    if len(pdf) < 10:
        return {
            "error": f"Insufficient data: {len(pdf)} rows (need ≥ 10)",
            "model": "AutoARIMA",
            "predictions": [],
        }

    sf = StatsForecast(
        models=[AutoARIMA(season_length=season_length)],
        freq="D",
        n_jobs=1,
    )

    fcst = sf.forecast(df=pdf[["unique_id", "ds", "y"]], h=horizon)

    predictions = []
    for _, row in fcst.iterrows():
        val    = float(row.get("AutoARIMA", 0) or 0)
        lo_key = next((k for k in row.index if "lo-95" in str(k)), None)
        hi_key = next((k for k in row.index if "hi-95" in str(k)), None)
        predictions.append({
            "timestamp":   str(row["ds"])[:10],
            "value":       round(val, 4),
            "lower_bound": round(float(row[lo_key] or val), 4) if lo_key else round(val * 0.9, 4),
            "upper_bound": round(float(row[hi_key] or val), 4) if hi_key else round(val * 1.1, 4),
        })

    logger.info(
        "arima_complete",
        rows_trained=len(pdf),
        horizon=horizon,
        season_length=season_length,
    )

    return {
        "model":         "AutoARIMA",
        "predictions":   predictions,
        "training_rows": len(pdf),
    }
