"""PostgresInsightRepository — InsightReport repository backed by Postgres."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.insight.entities.insight_report import InsightReport
from backend.domain.insight.repositories.insight_repository import InsightRepository
from backend.infrastructure.persistence.models.insight_model import InsightReportModel


class PostgresInsightRepository(InsightRepository):
    """SQLAlchemy async implementation of InsightRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, entity_id: str) -> InsightReport | None:
        row = await self._session.get(InsightReportModel, entity_id)
        return self._to_entity(row) if row else None

    async def save(self, entity: InsightReport) -> InsightReport:
        existing = await self._session.get(InsightReportModel, entity.id)
        if existing:
            self._update_model(existing, entity)
        else:
            self._session.add(self._to_model(entity))
        return entity

    async def delete(self, entity_id: str) -> None:
        row = await self._session.get(InsightReportModel, entity_id)
        if row:
            await self._session.delete(row)

    async def get_by_dataset_id(self, dataset_id: str) -> InsightReport | None:
        result = await self._session.execute(
            select(InsightReportModel)
            .where(InsightReportModel.dataset_id == dataset_id)
            .order_by(InsightReportModel.generated_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def get_by_session_id(self, session_id: str) -> InsightReport | None:
        result = await self._session.execute(
            select(InsightReportModel)
            .where(InsightReportModel.session_id == session_id)
        )
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def list_by_dataset(self, dataset_id: str) -> list[InsightReport]:
        result = await self._session.execute(
            select(InsightReportModel)
            .where(InsightReportModel.dataset_id == dataset_id)
            .order_by(InsightReportModel.generated_at.desc())
        )
        return [self._to_entity(r) for r in result.scalars().all()]

    # ── Mapping ───────────────────────────────────────────────────────────

    @staticmethod
    def _to_entity(model: InsightReportModel) -> InsightReport:
        """Reconstruct InsightReport from the stored JSONB report_json."""
        report = InsightReport(
            id=model.id,
            session_id=model.session_id,
            dataset_id=model.dataset_id,
            is_critic_validated=model.is_critic_validated,
            has_forecasts=model.has_forecasts,
            report_pdf_key=model.report_pdf_key,
            generated_at=model.generated_at,
        )
        if model.report_json:
            report.executive_summary = model.report_json.get("executive_summary", "")
        return report

    @staticmethod
    def _to_model(entity: InsightReport) -> InsightReportModel:
        d = entity.to_dict()
        return InsightReportModel(
            id=entity.id,
            session_id=entity.session_id,
            dataset_id=entity.dataset_id,
            executive_summary={"text": entity.executive_summary},
            report_json=d,
            insight_count=len(entity.insights),
            has_forecasts=entity.has_forecasts,
            is_critic_validated=entity.is_critic_validated,
            report_pdf_key=entity.report_pdf_key,
            generated_at=entity.generated_at,
        )

    @staticmethod
    def _update_model(model: InsightReportModel, entity: InsightReport) -> None:
        d = entity.to_dict()
        model.report_json         = d
        model.executive_summary   = {"text": entity.executive_summary}
        model.insight_count       = len(entity.insights)
        model.has_forecasts       = entity.has_forecasts
        model.is_critic_validated = entity.is_critic_validated
        model.report_pdf_key      = entity.report_pdf_key
        model.generated_at        = entity.generated_at
