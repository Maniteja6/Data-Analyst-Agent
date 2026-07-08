"""AnalysisSession ORM model — maps to the ``analysis_sessions`` table."""

from __future__ import annotations

from datetime import datetime

from backend.infrastructure.persistence.database import Base
from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class SessionModel(Base):
    """ORM model for ``analysis_sessions``.

    One row per analytics pipeline run. The ``profile_json`` and
    ``cleaning_report_json`` columns store the DataProfile and
    CleaningReport entity snapshots after each pipeline stage.

    The ``anomaly_ids`` JSONB array stores the UUIDs of AnomalyAlert
    entities so they can be retrieved via the InsightRepository without
    storing alerts in a separate table.
    """

    __tablename__ = "analysis_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    cleaning_report_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    anomaly_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_sessions_dataset_id", "dataset_id"),
        Index("ix_sessions_status", "status"),
        Index("ix_sessions_dataset_status", "dataset_id", "status"),
    )
