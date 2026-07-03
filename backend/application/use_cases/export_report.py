"""ExportReportUseCase — enqueues report generation and returns the job ID."""
from __future__ import annotations

import structlog

from backend.application.commands.export_report_command import ExportReportCommand
from backend.domain.insight.exceptions import InsightReportNotFoundException

logger = structlog.get_logger(__name__)


class ExportReportUseCase:
    """Validates that an InsightReport exists, then enqueues the render job.

    The actual PDF/XLSX/PPTX generation happens in the ``reports`` Celery queue
    so it doesn't block the API response. The caller polls
    ``GET /api/v1/jobs/<job_id>`` for the download URL.
    """

    def __init__(self, insight_repo, job_service, cache) -> None:
        self._insight_repo = insight_repo
        self._job_service  = job_service
        self._cache        = cache

    async def execute(self, cmd: ExportReportCommand) -> dict:
        # Check cache first (avoids DB hit for common case)
        cached = await self._cache.get_json(f"insights:{cmd.dataset_id}")
        if not cached:
            report = await self._insight_repo.get_by_dataset_id(cmd.dataset_id)
            if report is None:
                raise InsightReportNotFoundException(cmd.dataset_id)

        job_id = self._job_service.enqueue_report(
            dataset_id=cmd.dataset_id,
            session_id=cmd.session_id,
            format=cmd.format,
        )
        logger.info("export_enqueued", dataset_id=cmd.dataset_id, format=cmd.format, job_id=job_id)
        return {
            "job_id":     job_id,
            "format":     cmd.format,
            "dataset_id": cmd.dataset_id,
            "status":     "queued",
        }
