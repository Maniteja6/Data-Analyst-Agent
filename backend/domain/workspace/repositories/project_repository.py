"""ProjectRepository — abstract port for Project entity persistence."""
from __future__ import annotations

from abc import abstractmethod

from backend.shared.repository import Repository
from backend.domain.workspace.entities.project import Project


class ProjectRepository(Repository[Project, str]):
    """Abstract repository for Project entities.

    Projects are lightweight grouping entities so the full project (including
    dataset_ids and conversation_ids lists) fits in a single Postgres row
    stored as JSONB arrays — no separate join table needed.

    Concrete implementation:
    ``backend/infrastructure/persistence/repositories/postgres_project_repository.py``
    """

    @abstractmethod
    async def get_by_id(self, entity_id: str) -> Project | None:
        """Return a Project by UUID, or None if not found or archived."""

    @abstractmethod
    async def save(self, entity: Project) -> Project:
        """Insert or update a Project."""

    @abstractmethod
    async def delete(self, entity_id: str) -> None:
        """Soft-delete (archive) a Project by UUID."""

    @abstractmethod
    async def get_by_owner(self, owner_id: str) -> list[Project]:
        """Return all non-archived projects for an owner, newest first.

        Used to populate the project list in the sidebar.
        """

    @abstractmethod
    async def get_by_dataset_id(self, dataset_id: str) -> Project | None:
        """Return the Project that contains a given dataset, or None.

        Used by the upload use case to auto-add new datasets to an existing
        project when the upload request includes a project_id.
        """

    @abstractmethod
    async def list_active(self) -> list[Project]:
        """Return all non-archived projects across all owners.

        Admin-only endpoint — used by the management dashboard.
        """

    @abstractmethod
    async def count_by_owner(self, owner_id: str) -> int:
        """Count active projects for an owner."""
