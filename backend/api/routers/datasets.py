"""Dataset CRUD and upload endpoints."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import structlog
from backend.api.dependencies import (
    get_dataset_repo,
    get_get_dataset_use_case,
    get_upload_use_case,
)
from backend.api.schemas.dataset_schemas import (
    DatasetListResponse,
    DatasetStatusResponse,
    DatasetUploadResponse,
    DeleteDatasetResponse,
)
from backend.application.commands.upload_dataset_command import UploadDatasetCommand
from backend.application.queries.get_dataset_query import GetDatasetQuery
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

if TYPE_CHECKING:
    from backend.application.use_cases.get_dataset import GetDatasetUseCase
    from backend.application.use_cases.upload_dataset import UploadDatasetUseCase
    from backend.domain.dataset.repositories.dataset_repository import DatasetRepository

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/datasets", tags=["datasets"])


@router.post("/upload", response_model=DatasetUploadResponse, status_code=201)
async def upload_dataset(
    file: UploadFile = File(..., description="Dataset file to upload"),
    project_id: str | None = Form(None),
    correlation_id: str | None = Form(None),
    use_case: UploadDatasetUseCase = Depends(get_upload_use_case),
) -> DatasetUploadResponse:
    """Upload a dataset file and start the analytics pipeline.

    Supported formats: CSV, TSV, XLSX, XLS, Parquet, JSON, JSONL.
    Returns a ``job_id`` to poll for analysis progress.
    """
    mime_type = file.content_type or "application/octet-stream"
    correlation_id = correlation_id or str(uuid.uuid4())
    size_bytes = 0
    content = await file.read()
    size_bytes = len(content)

    import io

    cmd = UploadDatasetCommand(
        filename=file.filename or "upload",
        file_obj=io.BytesIO(content),
        size_bytes=size_bytes,
        mime_type=mime_type,
        project_id=project_id,
        correlation_id=correlation_id,
    )
    result = await use_case.execute(cmd)
    return DatasetUploadResponse(**result, message="Upload received. Analysis queued.")


@router.get("/{dataset_id}", response_model=DatasetStatusResponse)
async def get_dataset(
    dataset_id: str,
    use_case: GetDatasetUseCase = Depends(get_get_dataset_use_case),
) -> DatasetStatusResponse:
    """Get the status and metadata of a dataset."""
    query = GetDatasetQuery(dataset_id=dataset_id)
    result = await use_case.execute(query)
    return DatasetStatusResponse(
        **result.__dict__,
        size_mb=round(result.size_bytes / (1024**2), 2),
        progress_pct=_status_to_progress(result.status),
    )


@router.get("/", response_model=DatasetListResponse)
async def list_datasets(
    project_id: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    repo: DatasetRepository = Depends(get_dataset_repo),
) -> DatasetListResponse:
    """List datasets, optionally filtered by project."""
    if project_id:
        datasets = await repo.get_by_project(project_id)
    else:
        datasets = []  # admin-only without project filter

    items = [
        DatasetStatusResponse(
            id=d.id,
            original_name=d.original_name,
            status=d.status.value,
            size_bytes=d.size_bytes,
            size_mb=d.size_mb,
            mime_type=d.mime_type,
            project_id=d.project_id,
            has_schema=d.has_schema,
            has_time_series=d.has_time_series,
            schema_columns=[],
            created_at=d.created_at.isoformat() if d.created_at else None,
            updated_at=d.updated_at.isoformat() if d.updated_at else None,
            progress_pct=_status_to_progress(d.status.value),
        )
        for d in datasets[:limit]
    ]
    return DatasetListResponse(datasets=items, total=len(items))


@router.delete("/{dataset_id}", response_model=DeleteDatasetResponse)
async def delete_dataset(
    dataset_id: str,
    repo: DatasetRepository = Depends(get_dataset_repo),
) -> DeleteDatasetResponse:
    """Soft-delete a dataset (sets deleted_at; does not remove S3 file immediately)."""
    dataset = await repo.get_by_id(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    await repo.delete(dataset_id)
    return DeleteDatasetResponse(dataset_id=dataset_id)


def _status_to_progress(status: str) -> int:
    return {
        "uploaded": 5,
        "profiling": 25,
        "profiled": 50,
        "cleaning": 75,
        "ready": 100,
        "failed": 0,
    }.get(status, 0)
