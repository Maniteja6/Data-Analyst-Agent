"""GetJobStatusUseCase — retrieves job progress from Redis or Celery result backend."""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.application.queries.get_job_status_query import GetJobStatusQuery, JobStatusResult

if TYPE_CHECKING:
    from backend.application.ports.cache_port import ICacheService
    from backend.application.ports.job_port import IJobService


class GetJobStatusUseCase:
    """Returns the current status and progress of a background job.

    Priority:
    1. Redis job status hash (fast, set by Celery task during execution)
    2. Celery result backend (fallback when Redis has no entry)
    """

    def __init__(self, cache: ICacheService, job_service: IJobService) -> None:
        self._cache = cache
        self._job_service = job_service

    async def execute(self, query: GetJobStatusQuery) -> JobStatusResult:
        # Fast path: Redis hash written by the Celery task
        data = await self._cache.get_job_status(query.job_id)
        if data:
            return JobStatusResult(
                job_id=query.job_id,
                status=data.get("status", "pending"),
                progress=int(data.get("progress", 0)),
                step=data.get("step", ""),
                dataset_id=data.get("dataset_id"),
                error=data.get("error"),
            )

        # Fallback: Celery result backend
        celery_status = self._job_service.get_task_status(query.job_id)
        status = celery_status.get("status", "PENDING").lower()
        return JobStatusResult(
            job_id=query.job_id,
            status="complete"
            if status == "success"
            else ("failed" if status == "failure" else "pending"),
            progress=100 if status == "success" else 0,
            step="",
            error=str(celery_status.get("traceback", "")) if status == "failure" else None,
        )
