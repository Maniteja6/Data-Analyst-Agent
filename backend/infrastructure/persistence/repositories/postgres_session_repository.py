"""PostgresSessionRepository — AnalysisSession repository backed by Postgres."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.analytics.entities.analysis_session import AnalysisSession, SessionStatus
from backend.domain.analytics.repositories.session_repository import SessionRepository
from backend.infrastructure.persistence.models.session_model import SessionModel


class PostgresSessionRepository(SessionRepository):
    """SQLAlchemy async implementation of SessionRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, entity_id: str) -> AnalysisSession | None:
        row = await self._session.get(SessionModel, entity_id)
        return self._to_entity(row) if row else None

    async def save(self, entity: AnalysisSession) -> AnalysisSession:
        existing = await self._session.get(SessionModel, entity.id)
        if existing:
            self._update_model(existing, entity)
        else:
            self._session.add(self._to_model(entity))
        return entity

    async def delete(self, entity_id: str) -> None:
        row = await self._session.get(SessionModel, entity_id)
        if row:
            await self._session.delete(row)

    async def get_by_dataset_id(self, dataset_id: str) -> list[AnalysisSession]:
        result = await self._session.execute(
            select(SessionModel)
            .where(SessionModel.dataset_id == dataset_id)
            .order_by(SessionModel.started_at.desc())
        )
        return [self._to_entity(r) for r in result.scalars().all()]

    async def get_latest_by_dataset_id(self, dataset_id: str) -> AnalysisSession | None:
        result = await self._session.execute(
            select(SessionModel)
            .where(SessionModel.dataset_id == dataset_id)
            .order_by(SessionModel.started_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def get_by_status(self, status: SessionStatus) -> list[AnalysisSession]:
        result = await self._session.execute(
            select(SessionModel).where(SessionModel.status == status.value)
        )
        return [self._to_entity(r) for r in result.scalars().all()]

    async def count_by_dataset(self, dataset_id: str) -> int:
        from sqlalchemy import func
        result = await self._session.execute(
            select(func.count()).select_from(SessionModel)
            .where(SessionModel.dataset_id == dataset_id)
        )
        return result.scalar_one()

    # ── Mapping ───────────────────────────────────────────────────────────

    @staticmethod
    def _to_entity(model: SessionModel) -> AnalysisSession:
        return AnalysisSession(
            id=model.id,
            dataset_id=model.dataset_id,
            correlation_id=model.correlation_id,
            status=SessionStatus(model.status),
            error_message=model.error_message,
            started_at=model.started_at,
            completed_at=model.completed_at,
        )

    @staticmethod
    def _to_model(entity: AnalysisSession) -> SessionModel:
        return SessionModel(
            id=entity.id,
            dataset_id=entity.dataset_id,
            correlation_id=entity.correlation_id,
            status=entity.status.value,
            error_message=entity.error_message,
            started_at=entity.started_at,
            completed_at=entity.completed_at,
        )

    @staticmethod
    def _update_model(model: SessionModel, entity: AnalysisSession) -> None:
        model.status        = entity.status.value
        model.error_message = entity.error_message
        model.completed_at  = entity.completed_at
        if entity.profile:
            model.profile_json = entity.profile.to_dict() if hasattr(entity.profile, "to_dict") else entity.profile
        if entity.cleaning_report:
            model.cleaning_report_json = (
                entity.cleaning_report.to_dict()
                if hasattr(entity.cleaning_report, "to_dict") else entity.cleaning_report
            )
        if entity.anomaly_ids:
            model.anomaly_ids = entity.anomaly_ids
