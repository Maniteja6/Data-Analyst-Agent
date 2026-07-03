"""Job status polling endpoint."""
from __future__ import annotations
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from backend.api.dependencies import get_job_status_use_case
from backend.application.queries.get_job_status_query import GetJobStatusQuery

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


class JobStatusResponse(BaseModel):
    job_id:     str
    status:     str
    progress:   int
    step:       str
    dataset_id: str | None = None
    error:      str | None = None
    download_url: str | None = None


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id:   str,
    use_case=Depends(get_job_status_use_case),
):
    """Poll the status and progress of a background job (analysis, report generation)."""
    result = await use_case.execute(GetJobStatusQuery(job_id=job_id))
    return JobStatusResponse(
        job_id=result.job_id,
        status=result.status,
        progress=result.progress,
        step=result.step,
        dataset_id=result.dataset_id,
        error=result.error,
    )
