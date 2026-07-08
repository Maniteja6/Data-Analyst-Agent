"""AgentExecution ORM model — maps to the ``agent_executions`` table."""

from __future__ import annotations

from datetime import datetime

from backend.infrastructure.persistence.database import Base
from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class AgentExecutionModel(Base):
    """ORM model for ``agent_executions``.

    Append-only audit table. One row per agent invocation. Used for:
    - Debugging failed pipelines
    - Eval replay (same input → expected output)
    - Cost attribution (cost_usd per agent per session)
    - LLM response cache (input_hash lookup)

    Rows older than 30 days are archived to S3 via a Postgres ``pg_cron``
    job defined in migration 004.
    """

    __tablename__ = "agent_executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_agent_executions_session", "session_id"),
        Index("ix_agent_executions_agent", "agent_name"),
        Index("ix_agent_executions_input_hash", "agent_name", "input_hash"),
        # Partial index for fast LLM cache lookup (successful results only)
        Index(
            "ix_agent_executions_cache_lookup",
            "agent_name",
            "input_hash",
            postgresql_where="success = TRUE AND input_hash IS NOT NULL",
        ),
    )
