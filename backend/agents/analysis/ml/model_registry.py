"""MLflow model registry wrapper for logging AutoML runs.

Optional — only activates when MLflow is installed and
``MLFLOW_TRACKING_URI`` is set in the environment.
"""
from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

DEFAULT_EXPERIMENT = "datapilot-automl"


def log_model(
    model_result: dict,
    experiment_name: str = DEFAULT_EXPERIMENT,
) -> str | None:
    """Log an AutoML result to MLflow.

    Args:
        model_result:    Dict returned by ``run_automl()``.
        experiment_name: MLflow experiment name.

    Returns:
        MLflow run ID string, or None if logging fails or MLflow is absent.
    """
    try:
        import mlflow
        mlflow.set_experiment(experiment_name)
        with mlflow.start_run():
            mlflow.log_params({
                "task":        model_result.get("task"),
                "target":      model_result.get("target"),
                "model_type":  model_result.get("model_type", "Unknown"),
                "feature_count": model_result.get("feature_count", 0),
                "training_rows": model_result.get("training_rows", 0),
            })
            mlflow.log_metrics({
                "cv_score_mean": model_result.get("cv_score_mean", 0.0),
                "cv_score_std":  model_result.get("cv_score_std", 0.0),
            })
            run_id = mlflow.active_run().info.run_id
            logger.info("mlflow_run_logged", run_id=run_id, experiment=experiment_name)
            return run_id
    except ImportError:
        logger.debug("mlflow_not_installed")
        return None
    except Exception as exc:
        logger.warning("mlflow_log_failed", error=str(exc))
        return None


def get_best_run(experiment_name: str = DEFAULT_EXPERIMENT) -> dict | None:
    """Retrieve the best run from MLflow by cv_score_mean.

    Returns:
        Run info dict, or None if MLflow is not available.
    """
    try:
        import mlflow
        client = mlflow.tracking.MlflowClient()
        exp    = client.get_experiment_by_name(experiment_name)
        if not exp:
            return None
        runs = client.search_runs(
            experiment_ids=[exp.experiment_id],
            order_by=["metrics.cv_score_mean DESC"],
            max_results=1,
        )
        if not runs:
            return None
        run = runs[0]
        return {
            "run_id":        run.info.run_id,
            "cv_score_mean": run.data.metrics.get("cv_score_mean"),
            "task":          run.data.params.get("task"),
            "target":        run.data.params.get("target"),
        }
    except Exception as exc:
        logger.debug("mlflow_get_best_run_failed", error=str(exc))
        return None
