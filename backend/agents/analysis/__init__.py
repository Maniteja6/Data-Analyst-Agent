"""Agent sub-package."""
"""Analysis agents — parallel fan-out layer of the pipeline DAG.

All five agents run concurrently after the cleaning step:
    SQLAgent          — NL→SQL→DuckDB; emits sql:result
    PythonAgent       — LLM pandas codegen in subprocess sandbox
    ForecastAgent     — Prophet + AutoARIMA + XGBoost; emits forecast:complete
    MLAgent           — RandomForest AutoML; emits ml:complete
    VisualizationAgent— Vega-Lite v5 spec from result rows
"""
from backend.agents.analysis.sql.sql_agent                   import SQLAgent
from backend.agents.analysis.python.python_agent             import PythonAgent
from backend.agents.analysis.forecast.forecast_agent         import ForecastAgent
from backend.agents.analysis.ml.ml_agent                     import MLAgent
from backend.agents.analysis.visualization.visualization_agent import VisualizationAgent

__all__ = ["SQLAgent", "PythonAgent", "ForecastAgent", "MLAgent", "VisualizationAgent"]
