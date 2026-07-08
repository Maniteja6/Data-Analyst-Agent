"""GetDatasetQuery — query DTO and result for dataset retrieval."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GetDatasetQuery:
    dataset_id: str


@dataclass
class DatasetResult:
    id: str
    original_name: str
    status: str
    size_bytes: int
    row_count: int | None
    column_count: int | None
    mime_type: str
    project_id: str | None
    has_schema: bool
    has_time_series: bool
    schema_columns: list[dict]
    created_at: str | None
    updated_at: str | None
    error_message: str | None
