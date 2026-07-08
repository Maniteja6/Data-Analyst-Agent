"""Celery application factory and configuration.

DataPilot uses Celery for three categories of background work:

    analysis   — dataset upload → schema inference → profiling → cleaning → anomaly detection
    agents     — LangGraph DAG execution (Planner → SQL/Forecast/ML → Insight → Critic → Report)
    reports    — PDF/XLSX/PPTX generation from a completed InsightReport

Each category has a dedicated queue so they can be scaled independently:
    - Analysis workers need high CPU and large memory (pandas, polars, scikit-learn)
    - Agent workers need network access and moderate memory (Bedrock API calls)
    - Report workers need disk and optional WeasyPrint/Chrome headless (PDF)

Task routing maps each task module to its queue via ``task_routes``.

Usage::

    from backend.infrastructure.job_queue.celery_app import celery_app

    # Dispatch a task
    celery_app.send_task(
        "analysis.run_pipeline",
        kwargs={"dataset_id": "...", "storage_key": "...", "correlation_id": "..."},
        queue="analysis",
    )

Starting workers::

    # Analysis workers (high CPU)
    celery -A backend.infrastructure.job_queue.celery_app worker \\
        --queues=analysis --concurrency=2 --hostname=analysis@%h

    # Agent workers (Bedrock-bound)
    celery -A backend.infrastructure.job_queue.celery_app worker \\
        --queues=agents --concurrency=4 --hostname=agents@%h

    # Report workers
    celery -A backend.infrastructure.job_queue.celery_app worker \\
        --queues=reports --concurrency=2 --hostname=reports@%h
"""

from __future__ import annotations

from typing import Any

from backend.config.settings import get_settings
from celery import Celery
from celery.schedules import crontab
from celery.signals import task_failure, task_postrun, task_prerun, worker_ready

settings = get_settings()

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

celery_app = Celery(
    "datapilot",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "backend.infrastructure.job_queue.tasks.analysis_tasks",
        "backend.infrastructure.job_queue.tasks.agent_tasks",
        "backend.infrastructure.job_queue.tasks.report_tasks",
    ],
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

celery_app.conf.update(
    # Serialisation — JSON only (no pickle; avoids arbitrary code execution)
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Time limits
    # task_soft_time_limit: SIGTERM → raises SoftTimeLimitExceeded
    task_soft_time_limit=settings.celery_task_soft_time_limit,
    task_time_limit=settings.celery_task_time_limit,  # SIGKILL
    # Time zone
    timezone="UTC",
    enable_utc=True,
    # Result expiry — keep results for 1 hour (enough for the frontend to poll)
    result_expires=3600,
    # Worker behaviour
    # worker_prefetch_multiplier=1: one task per worker slot (prevents memory
    # spikes on analysis tasks)
    worker_prefetch_multiplier=1,
    task_acks_late=True,  # acknowledge only after success (allows retry on worker crash)
    task_reject_on_worker_lost=True,  # requeue if the worker process dies mid-task
    # Task routing — each task module → dedicated queue
    task_routes={
        "backend.infrastructure.job_queue.tasks.analysis_tasks.*": {"queue": "analysis"},
        "backend.infrastructure.job_queue.tasks.agent_tasks.*": {"queue": "agents"},
        "backend.infrastructure.job_queue.tasks.report_tasks.*": {"queue": "reports"},
    },
    # Default queue for tasks not matched by task_routes
    task_default_queue="celery",
    task_default_exchange="celery",
    # Beat schedule — periodic maintenance tasks
    beat_schedule={
        "cleanup-stale-jobs": {
            "task": "analysis.cleanup_stale_jobs",
            "schedule": crontab(minute="*/30"),  # every 30 minutes
        },
    },
)

# ---------------------------------------------------------------------------
# Signal handlers — for structured logging and OpenTelemetry tracing
# ---------------------------------------------------------------------------


@worker_ready.connect
def on_worker_ready(sender: Any, **kwargs: Any) -> None:  # noqa: ANN401 — Celery signal payload
    import structlog

    structlog.get_logger("celery.worker").info(
        "celery_worker_ready", queues=list(sender.app.amqp.queues.keys())
    )


@task_prerun.connect
def on_task_prerun(task_id: str, task: Any, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401 — Celery signal payload
    import structlog

    structlog.contextvars.bind_contextvars(
        celery_task_id=task_id,
        celery_task_name=task.name,
    )


@task_postrun.connect
def on_task_postrun(
    task_id: str,
    task: Any,  # noqa: ANN401
    retval: Any,  # noqa: ANN401
    state: str,
    *args: Any,  # noqa: ANN401
    **kwargs: Any,  # noqa: ANN401
) -> None:
    import structlog

    structlog.get_logger("celery.task").info(
        "celery_task_complete",
        task_id=task_id,
        task=task.name,
        state=state,
    )
    structlog.contextvars.clear_contextvars()


@task_failure.connect
def on_task_failure(
    task_id: str,
    exception: BaseException,
    traceback: Any,  # noqa: ANN401
    sender: Any,  # noqa: ANN401
    *args: Any,  # noqa: ANN401
    **kwargs: Any,  # noqa: ANN401
) -> None:
    import structlog

    structlog.get_logger("celery.task").error(
        "celery_task_failed",
        task_id=task_id,
        task=sender.name,
        error=str(exception),
    )
    structlog.contextvars.clear_contextvars()
