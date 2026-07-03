"""SessionRepository — abstract port for AnalysisSession persistence."""
from __future__ import annotations

from abc import abstractmethod

from backend.shared.repository import Repository
from backend.domain.analytics.entities.analysis_session import AnalysisSession, SessionStatus


class SessionRepository(Repository[AnalysisSession, str]):
    """Abstract repository for AnalysisSession aggregates.

    Concrete implementation lives in:
    ``backend/infrastructure/persistence/repositories/postgres_session_repository.py``

    Domain and application layers depend only on this interface, not on
    SQLAlchemy or any specific database.
    """

    @abstractmethod
    async def get_by_dataset_id(self, dataset_id: str) -> list[AnalysisSession]:
        """Return all sessions for a given dataset, newest first."""

    @abstractmethod
    async def get_latest_by_dataset_id(self, dataset_id: str) -> AnalysisSession | None:
        """Return the most recently created session for a dataset, or None."""

    @abstractmethod
    async def get_by_status(self, status: SessionStatus) -> list[AnalysisSession]:
        """Return all sessions in a given status — used by the monitoring dashboard."""

    @abstractmethod
    async def count_by_dataset(self, dataset_id: str) -> int:
        """Count total sessions for a dataset — used for pagination."""
