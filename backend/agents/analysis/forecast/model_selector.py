"""Selects the best forecast model from multiple runner outputs.

Comparison criteria (in order of priority):
1. Prefer results without errors
2. Lower MAPE (mean absolute percentage error) when cross-validation is available
3. Prophet is preferred over ARIMA when both succeed (better for business seasonality)
4. Fall through to XGBoost as last resort
"""
from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


def select_best_model(*results: dict) -> dict:
    """Return the best forecast result from multiple runner outputs.

    Args:
        *results: Variable number of result dicts, each from a forecast runner.
                  Each dict must have a ``model`` key and optionally ``mape``.

    Returns:
        The result dict with the best forecast, or an error dict if all failed.
    """
    valid = [r for r in results if "error" not in r and r.get("predictions")]

    if not valid:
        all_errors = [r.get("error", "Unknown error") for r in results]
        logger.warning("all_forecast_models_failed", errors=all_errors)
        return {
            "error":       "All forecast models failed",
            "model":       "None",
            "predictions": [],
            "errors":      all_errors,
        }

    # Prefer the model with lowest MAPE if available
    with_mape = [r for r in valid if r.get("mape") is not None]
    if with_mape:
        best = min(with_mape, key=lambda r: r["mape"])
        logger.info("model_selected_by_mape", model=best["model"], mape=best.get("mape"))
        return best

    # Fall back to model priority: Prophet > ARIMA > XGBoost
    priority = {"Prophet": 0, "AutoARIMA": 1, "XGBoost": 2}
    best = min(valid, key=lambda r: priority.get(r.get("model", ""), 99))
    logger.info("model_selected_by_priority", model=best.get("model"))
    return best


def compute_mape(actual: list[float], predicted: list[float]) -> float | None:
    """Compute Mean Absolute Percentage Error for model evaluation.

    Returns None when actual values contain zeros (undefined MAPE).
    """
    if len(actual) != len(predicted) or not actual:
        return None
    try:
        errors = [
            abs((a - p) / a)
            for a, p in zip(actual, predicted)
            if a != 0
        ]
        return round(sum(errors) / len(errors), 6) if errors else None
    except Exception:
        return None
