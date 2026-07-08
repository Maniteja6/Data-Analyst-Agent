"""Export request/response Pydantic schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ExportReportRequest(BaseModel):
    format: Literal["pdf", "xlsx", "pptx", "json"] = "pdf"


class ExportReportResponse(BaseModel):
    job_id: str
    format: str
    dataset_id: str
    status: str = "queued"
    message: str = "Report generation queued. Poll the job endpoint for the download URL."


class ExportReadyResponse(BaseModel):
    job_id: str
    format: str
    download_url: str
    expires_in: int = 900  # seconds
