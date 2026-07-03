"""Report export endpoints."""
from __future__ import annotations
from fastapi import APIRouter, Depends
import structlog

from backend.api.dependencies import get_export_report_use_case
from backend.api.schemas.export_schemas import ExportReportRequest, ExportReportResponse
from backend.application.commands.export_report_command import ExportReportCommand

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/exports", tags=["exports"])


@router.post("/{dataset_id}", response_model=ExportReportResponse, status_code=202)
async def export_report(
    dataset_id: str,
    body:       ExportReportRequest,
    use_case=Depends(get_export_report_use_case),
):
    """Queue a report export. Poll ``GET /api/v1/jobs/{job_id}`` for the download URL."""
    cmd    = ExportReportCommand(dataset_id=dataset_id, session_id="", format=body.format)
    result = await use_case.execute(cmd)
    return ExportReportResponse(**result, message="Report generation queued. Poll the job endpoint for the download URL.")
