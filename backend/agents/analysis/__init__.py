"""Agent sub-package.

Analysis agents — parallel fan-out layer of the pipeline DAG.

All five agents run concurrently after the cleaning step:
    SQLAgent          — NL→SQL→DuckDB; emits sql:result
    PythonAgent       — LLM pandas codegen in subprocess sandbox
    ForecastAgent     — Prophet + AutoARIMA + XGBoost; emits forecast:complete
    MLAgent           — RandomForest AutoML; emits ml:complete
    VisualizationAgent— Vega-Lite v5 spec from result rows
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = ["SQLAgent", "PythonAgent", "ForecastAgent", "MLAgent", "VisualizationAgent"]


def __getattr__(name: str) -> Any:
    mapping = {
        "SQLAgent": ("backend.agents.analysis.sql.sql_agent", "SQLAgent"),
        "PythonAgent": ("backend.agents.analysis.python.python_agent", "PythonAgent"),
        "ForecastAgent": ("backend.agents.analysis.forecast.forecast_agent", "ForecastAgent"),
        "MLAgent": ("backend.agents.analysis.ml.ml_agent", "MLAgent"),
        "VisualizationAgent": (
            "backend.agents.analysis.visualization.visualization_agent",
            "VisualizationAgent",
        ),
    }
    if name not in mapping:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = mapping[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
