"""InsightRepository — abstract port for InsightReport persistence."""

from __future__ import annotations

from abc import abstractmethod

from backend.domain.insight.entities.insight_report import InsightReport
from backend.shared.repository import Repository


class InsightRepository(Repository[InsightReport, str]):
    """Abstract repository for InsightReport aggregates.

    Concrete implementation lives in:
    ``backend/infrastructure/persistence/repositories/postgres_insight_repository.py``
    """

    @abstractmethod
    async def get_by_dataset_id(self, dataset_id: str) -> InsightReport | None:
        """Return the most recently generated report for a dataset, or None."""

    @abstractmethod
    async def get_by_session_id(self, session_id: str) -> InsightReport | None:
        """Return the report generated for a specific analysis session, or None."""

    @abstractmethod
    async def list_by_dataset(self, dataset_id: str) -> list[InsightReport]:
        """Return all reports ever generated for a dataset, newest first."""
