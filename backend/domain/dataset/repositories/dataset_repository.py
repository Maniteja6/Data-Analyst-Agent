"""DatasetRepository — abstract port for Dataset aggregate persistence."""
from __future__ import annotations

from abc import abstractmethod

from backend.shared.repository import Repository
from backend.domain.dataset.entities.dataset import Dataset
from backend.domain.dataset.value_objects.dataset_status import DatasetStatus


class DatasetRepository(Repository[Dataset, str]):
    """Abstract repository for Dataset aggregates.

    Concrete implementation:
    ``backend/infrastructure/persistence/repositories/postgres_dataset_repository.py``

    All methods must handle soft-delete correctly — deleted datasets
    (``deleted_at IS NOT NULL``) must be excluded from all queries except
    ``get_by_id`` when explicitly requested for audit purposes.
    """

    @abstractmethod
    async def get_by_id(self, entity_id: str) -> Dataset | None:
        """Return a Dataset by its UUID, or None if not found or soft-deleted."""

    @abstractmethod
    async def save(self, entity: Dataset) -> Dataset:
        """Insert or update a Dataset. Sets ``updated_at`` to UTC now."""

    @abstractmethod
    async def delete(self, entity_id: str) -> None:
        """Soft-delete a Dataset by setting ``deleted_at`` to UTC now."""

    @abstractmethod
    async def get_by_project(self, project_id: str) -> list[Dataset]:
        """Return all non-deleted datasets for a project, newest first."""

    @abstractmethod
    async def get_by_status(self, status: DatasetStatus) -> list[Dataset]:
        """Return all non-deleted datasets in the given status.

        Used by the monitoring worker to find stuck PROFILING/CLEANING
        sessions and re-queue them.
        """

    @abstractmethod
    async def get_by_checksum(self, checksum_sha256: str) -> Dataset | None:
        """Return an existing non-deleted dataset with the given SHA-256 checksum.

        Used by ``UploadDatasetUseCase`` to detect and prevent duplicate uploads.
        """

    @abstractmethod
    async def count_by_project(self, project_id: str) -> int:
        """Count total non-deleted datasets for a project."""
