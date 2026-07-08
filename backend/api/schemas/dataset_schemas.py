"""Dataset request/response Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DatasetUploadResponse(BaseModel):
    dataset_id: str
    job_id: str
    status: str = "uploaded"
    message: str = "Upload received. Analysis queued."


class DatasetStatusResponse(BaseModel):
    id: str
    original_name: str
    status: str
    size_bytes: int
    size_mb: float
    row_count: int | None = None
    column_count: int | None = None
    mime_type: str
    project_id: str | None = None
    has_schema: bool = False
    has_time_series: bool = False
    schema_columns: list[dict] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
    error_message: str | None = None
    progress_pct: int = 0


class DatasetListResponse(BaseModel):
    datasets: list[DatasetStatusResponse]
    total: int


class DeleteDatasetResponse(BaseModel):
    dataset_id: str
    message: str = "Dataset deleted successfully."
