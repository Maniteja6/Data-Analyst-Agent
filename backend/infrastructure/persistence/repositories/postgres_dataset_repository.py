"""PostgresDatasetRepository — concrete Dataset repository backed by Postgres."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.domain.dataset.entities.dataset import Dataset
from backend.domain.dataset.repositories.dataset_repository import DatasetRepository
from backend.domain.dataset.value_objects.dataset_status import DatasetStatus
from backend.infrastructure.persistence.models.dataset_model import DatasetModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession


class PostgresDatasetRepository(DatasetRepository):
    """SQLAlchemy async implementation of DatasetRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── CRUD ──────────────────────────────────────────────────────────────

    async def get_by_id(self, entity_id: str) -> Dataset | None:
        result = await self._session.execute(
            select(DatasetModel).where(
                DatasetModel.id == entity_id,
                DatasetModel.deleted_at.is_(None),
            )
        )
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def save(self, entity: Dataset) -> Dataset:
        existing = await self._session.get(DatasetModel, entity.id)
        if existing:
            self._update_model(existing, entity)
        else:
            model = self._to_model(entity)
            self._session.add(model)
        return entity

    async def delete(self, entity_id: str) -> None:
        await self._session.execute(
            update(DatasetModel)
            .where(DatasetModel.id == entity_id)
            .values(deleted_at=datetime.now(UTC))
        )

    # ── Domain queries ────────────────────────────────────────────────────

    async def get_by_project(self, project_id: str) -> list[Dataset]:
        result = await self._session.execute(
            select(DatasetModel)
            .where(
                DatasetModel.project_id == project_id,
                DatasetModel.deleted_at.is_(None),
            )
            .order_by(DatasetModel.created_at.desc())
        )
        return [self._to_entity(r) for r in result.scalars().all()]

    async def get_by_status(self, status: DatasetStatus) -> list[Dataset]:
        result = await self._session.execute(
            select(DatasetModel).where(
                DatasetModel.status == status.value,
                DatasetModel.deleted_at.is_(None),
            )
        )
        return [self._to_entity(r) for r in result.scalars().all()]

    async def get_by_checksum(self, checksum_sha256: str) -> Dataset | None:
        result = await self._session.execute(
            select(DatasetModel).where(
                DatasetModel.checksum_sha256 == checksum_sha256,
                DatasetModel.deleted_at.is_(None),
            )
        )
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def count_by_project(self, project_id: str) -> int:
        from sqlalchemy import func

        result = await self._session.execute(
            select(func.count())
            .select_from(DatasetModel)
            .where(
                DatasetModel.project_id == project_id,
                DatasetModel.deleted_at.is_(None),
            )
        )
        return result.scalar_one()

    # ── Mapping helpers ───────────────────────────────────────────────────

    @staticmethod
    def _to_entity(model: DatasetModel) -> Dataset:
        return Dataset(
            id=model.id,
            project_id=model.project_id,
            original_name=model.original_name,
            storage_key=model.storage_key,
            size_bytes=model.size_bytes,
            mime_type=model.mime_type,
            status=DatasetStatus(model.status),
            row_count=model.row_count,
            column_count=model.column_count,
            checksum_sha256=model.checksum_sha256,
            schema_json=model.schema_json,
            error_message=model.error_message,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_model(entity: Dataset) -> DatasetModel:
        return DatasetModel(
            id=entity.id,
            project_id=entity.project_id,
            original_name=entity.original_name,
            storage_key=entity.storage_key,
            size_bytes=entity.size_bytes,
            mime_type=entity.mime_type,
            status=entity.status.value,
            row_count=entity.row_count,
            column_count=entity.column_count,
            checksum_sha256=entity.checksum_sha256,
            schema_json=entity.schema_json,
            error_message=entity.error_message,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    @staticmethod
    def _update_model(model: DatasetModel, entity: Dataset) -> None:
        model.status = entity.status.value
        model.row_count = entity.row_count
        model.column_count = entity.column_count
        model.schema_json = entity.schema_json
        model.error_message = entity.error_message
        model.updated_at = entity.updated_at or datetime.now(UTC)
