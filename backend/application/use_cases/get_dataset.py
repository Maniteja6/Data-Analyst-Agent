"""GetDatasetUseCase — retrieves a dataset and its schema."""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.application.queries.get_dataset_query import DatasetResult, GetDatasetQuery
from backend.domain.dataset.exceptions import DatasetNotFoundError

if TYPE_CHECKING:
    from backend.domain.dataset.repositories.dataset_repository import DatasetRepository


class GetDatasetUseCase:
    def __init__(self, dataset_repo: DatasetRepository) -> None:
        self._repo = dataset_repo

    async def execute(self, query: GetDatasetQuery) -> DatasetResult:
        dataset = await self._repo.get_by_id(query.dataset_id)
        if dataset is None:
            raise DatasetNotFoundError(query.dataset_id)

        schema_cols = []
        if dataset.schema_json:
            schema_cols = dataset.schema_json.get("columns", [])

        return DatasetResult(
            id=dataset.id,
            original_name=dataset.original_name,
            status=dataset.status.value,
            size_bytes=dataset.size_bytes,
            row_count=dataset.row_count,
            column_count=dataset.column_count,
            mime_type=dataset.mime_type,
            project_id=dataset.project_id,
            has_schema=dataset.has_schema,
            has_time_series=dataset.has_time_series,
            schema_columns=schema_cols,
            created_at=dataset.created_at.isoformat() if dataset.created_at else None,
            updated_at=dataset.updated_at.isoformat() if dataset.updated_at else None,
            error_message=dataset.error_message,
        )
