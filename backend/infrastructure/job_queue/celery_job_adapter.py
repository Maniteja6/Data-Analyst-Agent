"""CeleryJobAdapter — implements the IJobService port using Celery.

The ``IJobService`` port (defined in ``application/ports/job_port.py``)
abstracts the job queue so that use cases and domain services never
import Celery directly. This adapter provides the concrete implementation.

Injected into use cases via ``api/dependencies.py``:

    def get_upload_use_case(session=...) -> UploadDatasetUseCase:
        return UploadDatasetUseCase(
            ...
            job_service=CeleryJobAdapter(),
        )

In tests, a ``MockJobAdapter`` or ``NullJobAdapter`` is substituted so
the test suite does not need a running Redis broker.

Usage::

    from backend.infrastructure.job_queue.celery_job_adapter import CeleryJobAdapter

    jobs = CeleryJobAdapter()
    job_id = jobs.enqueue_analysis(
        dataset_id="abc-123",
        storage_key="datasets/abc-123/sales.csv",
        correlation_id="req-456",
    )
    print(job_id)  # Celery task UUID
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


class CeleryJobAdapter:
    """Concrete IJobService implementation backed by Celery.

    All ``enqueue_*`` methods are synchronous (return immediately) because
    Celery's ``apply_async`` itself is synchronous — it publishes to the broker
    and returns a task ID without waiting for the worker to start.

    The returned task ID is the Celery-assigned UUID, which is stored in the
    job status cache under ``job:<task_id>`` so the frontend can poll
    ``GET /api/v1/jobs/<task_id>`` for progress.
    """

    def enqueue_analysis(
        self,
        dataset_id: str,
        storage_key: str,
        correlation_id: str,
    ) -> str:
        """Enqueue the full analytics pipeline for a newly uploaded dataset.

        Routes to the ``analysis`` queue:
        schema inference → profiling → cleaning → anomaly detection.

        Args:
            dataset_id:     UUID of the uploaded Dataset aggregate.
            storage_key:    S3/MinIO object key for the raw file.
            correlation_id: Request-scoped tracing ID propagated from the upload.

        Returns:
            Celery task UUID (use as ``job_id`` for status polling).
        """
        from backend.infrastructure.job_queue.tasks.analysis_tasks import run_analysis_pipeline

        result = run_analysis_pipeline.apply_async(
            kwargs={
                "dataset_id": dataset_id,
                "storage_key": storage_key,
                "correlation_id": correlation_id,
            },
            queue="analysis",
            task_id=None,  # let Celery generate the UUID
        )
        logger.info(
            "analysis_pipeline_enqueued",
            task_id=result.id,
            dataset_id=dataset_id,
        )
        return result.id

    def enqueue_agents(
        self,
        dataset_id: str,
        session_id: str,
        correlation_id: str,
    ) -> str:
        """Enqueue the AI agent pipeline after the analytics pipeline completes.

        Routes to the ``agents`` queue:
        PlannerAgent → DAGExecutor → InsightAgent → CriticAgent → RecommendationAgent.

        Called automatically by ``AnalyticsCompletedConsumer`` when the
        ``analytics.cleaning-complete`` Kafka event is received; or can be
        called directly from the ``RunAnalysisUseCase`` for re-analysis.

        Args:
            dataset_id:     Source dataset UUID.
            session_id:     Analysis session UUID (created by the RunAnalysis use case).
            correlation_id: Tracing ID from the originating request.

        Returns:
            Celery task UUID.
        """
        from backend.infrastructure.job_queue.tasks.agent_tasks import run_agent_pipeline

        result = run_agent_pipeline.apply_async(
            kwargs={
                "dataset_id": dataset_id,
                "session_id": session_id,
                "correlation_id": correlation_id,
            },
            queue="agents",
        )
        logger.info(
            "agent_pipeline_enqueued",
            task_id=result.id,
            dataset_id=dataset_id,
            session_id=session_id,
        )
        return result.id

    def enqueue_report(
        self,
        dataset_id: str,
        session_id: str,
        format: str,
        report_id: str | None = None,
    ) -> str:
        """Enqueue report generation for a completed InsightReport.

        Routes to the ``reports`` queue.
        Supported formats: ``'pdf'``, ``'xlsx'``, ``'pptx'``, ``'json'``.

        Args:
            dataset_id:  Source dataset UUID.
            session_id:  Analysis session whose InsightReport is to be exported.
            format:      Output format: ``'pdf'`` | ``'xlsx'`` | ``'pptx'`` | ``'json'``.
            report_id:   Optional InsightReport UUID (resolved from session if None).

        Returns:
            Celery task UUID — used as the ``job_id`` returned by the export endpoint.
        """
        from backend.infrastructure.job_queue.tasks.report_tasks import generate_report

        result = generate_report.apply_async(
            kwargs={
                "dataset_id": dataset_id,
                "session_id": session_id,
                "format": format,
                "report_id": report_id,
            },
            queue="reports",
        )
        logger.info(
            "report_generation_enqueued",
            task_id=result.id,
            dataset_id=dataset_id,
            format=format,
        )
        return result.id

    def get_task_status(self, task_id: str) -> dict:
        """Return the current status of a Celery task.

        Queries the Celery result backend (Redis) directly.
        Used as a fallback when the job status cache has no entry.

        Returns:
            Dict with keys: ``status``, ``result``, ``traceback``.
        """
        from backend.infrastructure.job_queue.celery_app import celery_app
        from celery.result import AsyncResult

        result = AsyncResult(task_id, app=celery_app)
        return {
            "task_id": task_id,
            "status": result.status,  # PENDING / STARTED / SUCCESS / FAILURE / RETRY
            "result": result.result if result.ready() else None,
            "traceback": result.traceback if result.failed() else None,
        }

    def revoke_task(self, task_id: str, terminate: bool = False) -> None:
        """Cancel a queued or running task.

        Args:
            task_id:   Celery task UUID to cancel.
            terminate: When True, sends SIGTERM to the worker process running
                       the task. Use with caution in production.
        """
        from backend.infrastructure.job_queue.celery_app import celery_app

        celery_app.control.revoke(task_id, terminate=terminate)
        logger.info("task_revoked", task_id=task_id, terminate=terminate)


class NullJobAdapter:
    """No-op IJobService implementation used in unit tests and local dev
    without a running broker.

    All ``enqueue_*`` methods return a deterministic fake UUID so test code
    can assert on the returned job_id without needing Celery running.
    """

    def __init__(self, fake_task_id: str = "00000000-0000-0000-0000-000000000000") -> None:
        self._fake_id = fake_task_id
        self.calls: list[dict] = []  # track enqueue calls for test assertions

    def enqueue_analysis(self, dataset_id: str, storage_key: str, correlation_id: str) -> str:
        self.calls.append({"method": "enqueue_analysis", "dataset_id": dataset_id})
        return self._fake_id

    def enqueue_agents(self, dataset_id: str, session_id: str, correlation_id: str) -> str:
        self.calls.append({"method": "enqueue_agents", "dataset_id": dataset_id})
        return self._fake_id

    def enqueue_report(
        self, dataset_id: str, session_id: str, format: str, report_id: str | None = None
    ) -> str:
        self.calls.append({"method": "enqueue_report", "format": format})
        return self._fake_id

    def get_task_status(self, task_id: str) -> dict:
        return {"task_id": task_id, "status": "SUCCESS", "result": None}

    def revoke_task(self, task_id: str, terminate: bool = False) -> None:
        self.calls.append({"method": "revoke_task", "task_id": task_id})
