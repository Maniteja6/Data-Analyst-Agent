"""Agent sub-package."""
"""ML agent — RandomForest AutoML with 3-fold cross-validation.

Auto-detects classification vs regression from target column dtype.
Feature engineering: median imputation + one-hot encoding for low-cardinality cats.
Optional: logs run to MLflow when MLFLOW_TRACKING_URI is set.
"""
from backend.agents.analysis.ml.ml_agent         import MLAgent
from backend.agents.analysis.ml.auto_ml_pipeline import run_automl
from backend.agents.analysis.ml.feature_engineer import engineer_features

__all__ = ["MLAgent", "run_automl", "engineer_features"]
