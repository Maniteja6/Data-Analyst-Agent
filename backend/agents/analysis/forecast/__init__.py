"""Forecast agent — time-series forecasting with model selection.

Runners:    ProphetRunner, AutoARIMARunner, XGBoostForecaster
Selector:   select_best_model() — MAPE-first, then Prophet > ARIMA > XGBoost
Detector:   is_forecasting_viable() — checks datetime cols + min row count
Real-time:  emits forecast:complete with trend_direction and predictions list.
"""

from backend.agents.analysis.forecast.forecast_agent import ForecastAgent
from backend.agents.analysis.forecast.model_selector import select_best_model
from backend.agents.analysis.forecast.ts_detector import is_forecasting_viable

__all__ = ["ForecastAgent", "is_forecasting_viable", "select_best_model"]

