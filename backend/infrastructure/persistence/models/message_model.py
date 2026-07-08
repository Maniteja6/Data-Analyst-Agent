"""Message ORM model — optional separate messages table.

NOTE: In the default configuration, messages are stored as JSONB inside
``conversations.messages`` (see ``ConversationModel``). This model provides
a normalised alternative for deployments that need full-text search,
row-level audit, or GDPR per-message erasure.

Enable by setting ``FEATURE_SEPARATE_MESSAGES_TABLE=true`` — the
``PostgresConversationRepository`` switches to writing here instead of
the JSONB column.
"""

from __future__ import annotations

from datetime import datetime

from backend.infrastructure.persistence.database import Base
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class MessageModel(Base):
    """ORM model for ``messages`` (optional normalised table)."""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    citations: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    visualizations: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    agent_trace: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_messages_conversation_id", "conversation_id"),
        Index("ix_messages_role", "role"),
    )
