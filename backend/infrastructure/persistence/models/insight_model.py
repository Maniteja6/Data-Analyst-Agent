"""InsightReport ORM model — maps to the ``insight_reports`` table."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.infrastructure.persistence.database import Base


class InsightReportModel(Base):
    """ORM model for ``insight_reports``.

    The full InsightReport aggregate is stored as a single JSONB document
    in ``report_json``. This avoids complex joins across insights, KPIs,
    anomalies, forecasts, and recommendations while keeping all related
    data retrievable in one query.

    The ``report_pdf_key`` is populated asynchronously by the ReportAgent
    after PDF generation completes.
    """

    __tablename__ = "insight_reports"

    id:                  Mapped[str]           = mapped_column(String(36),  primary_key=True)
    session_id:          Mapped[str]           = mapped_column(
        String(36), ForeignKey("analysis_sessions.id", ondelete="CASCADE"), nullable=False
    )
    dataset_id:          Mapped[str]           = mapped_column(
        String(36), ForeignKey("datasets.id",          ondelete="CASCADE"), nullable=False
    )
    executive_summary:   Mapped[str | None]    = mapped_column(JSONB,        nullable=True)   # stored as text inside JSONB
    report_json:         Mapped[dict | None]   = mapped_column(JSONB,        nullable=True)
    insight_count:       Mapped[int]           = mapped_column(Integer,      nullable=False, default=0)
    has_forecasts:       Mapped[bool]          = mapped_column(Boolean,      nullable=False, default=False)
    is_critic_validated: Mapped[bool]          = mapped_column(Boolean,      nullable=False, default=False)
    report_pdf_key:      Mapped[str | None]    = mapped_column(String(1024), nullable=True)
    generated_at:        Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_insight_reports_dataset_id",  "dataset_id"),
        Index("ix_insight_reports_session_id",  "session_id"),
        # GIN index on JSONB for fast jsonb_path_exists / @> queries
        Index("ix_insight_reports_json_gin",    "report_json", postgresql_using="gin"),
    )
