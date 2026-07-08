"""PostgresConversationRepository — Conversation repository backed by Postgres."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.domain.workspace.entities.conversation import Conversation
from backend.domain.workspace.entities.message import Message
from backend.domain.workspace.repositories.conversation_repository import ConversationRepository
from backend.domain.workspace.value_objects.message_role import MessageRole
from backend.infrastructure.persistence.models.conversation_model import ConversationModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession


class PostgresConversationRepository(ConversationRepository):
    """SQLAlchemy async implementation of ConversationRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, entity_id: str) -> Conversation | None:
        result = await self._session.execute(
            select(ConversationModel).where(
                ConversationModel.id == entity_id,
                ConversationModel.deleted_at.is_(None),
            )
        )
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def save(self, entity: Conversation) -> Conversation:
        existing = await self._session.get(ConversationModel, entity.id)
        if existing:
            self._update_model(existing, entity)
        else:
            self._session.add(self._to_model(entity))
        return entity

    async def delete(self, entity_id: str) -> None:
        await self._session.execute(
            update(ConversationModel)
            .where(ConversationModel.id == entity_id)
            .values(deleted_at=datetime.now(UTC))
        )

    async def get_by_dataset_id(self, dataset_id: str) -> list[Conversation]:
        result = await self._session.execute(
            select(ConversationModel)
            .where(
                ConversationModel.dataset_id == dataset_id,
                ConversationModel.deleted_at.is_(None),
            )
            .order_by(ConversationModel.updated_at.desc())
        )
        return [self._to_entity(r) for r in result.scalars().all()]

    async def get_by_project_id(self, project_id: str) -> list[Conversation]:
        # Conversations are linked to datasets, not projects directly.
        # This requires a JOIN via the dataset_id → project_id relationship.
        from backend.infrastructure.persistence.models.dataset_model import DatasetModel

        stmt = (
            select(ConversationModel)
            .join(DatasetModel, ConversationModel.dataset_id == DatasetModel.id)
            .where(
                DatasetModel.project_id == project_id,
                ConversationModel.deleted_at.is_(None),
            )
            .order_by(ConversationModel.updated_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(r) for r in result.scalars().all()]

    async def get_active_by_dataset_id(self, dataset_id: str) -> Conversation | None:
        result = await self._session.execute(
            select(ConversationModel)
            .where(
                ConversationModel.dataset_id == dataset_id,
                not ConversationModel.is_closed,
                ConversationModel.deleted_at.is_(None),
            )
            .order_by(ConversationModel.updated_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return self._to_entity(row) if row else None

    async def count_by_dataset(self, dataset_id: str) -> int:
        from sqlalchemy import func

        result = await self._session.execute(
            select(func.count())
            .select_from(ConversationModel)
            .where(
                ConversationModel.dataset_id == dataset_id,
                ConversationModel.deleted_at.is_(None),
            )
        )
        return result.scalar_one()

    async def search_by_content(
        self, dataset_id: str, query: str, limit: int = 10
    ) -> list[Conversation]:
        """Full-text search over JSONB messages using PostgreSQL ILIKE."""
        from sqlalchemy import func
        from sqlalchemy.dialects.postgresql import TEXT

        result = await self._session.execute(
            select(ConversationModel)
            .where(
                ConversationModel.dataset_id == dataset_id,
                ConversationModel.deleted_at.is_(None),
                func.cast(ConversationModel.messages, TEXT).ilike(f"%{query}%"),
            )
            .order_by(ConversationModel.updated_at.desc())
            .limit(limit)
        )
        return [self._to_entity(r) for r in result.scalars().all()]

    # ── Mapping ───────────────────────────────────────────────────────────

    @staticmethod
    def _to_entity(model: ConversationModel) -> Conversation:
        messages = []
        for m in model.messages or []:
            messages.append(
                Message(
                    id=m.get("id", ""),
                    conversation_id=model.id,
                    role=MessageRole.from_string(m.get("role", "user")),
                    content=m.get("content", ""),
                    citations=m.get("citations", []),
                    visualizations=m.get("visualizations", []),
                )
            )
        return Conversation(
            id=model.id,
            dataset_id=model.dataset_id,
            title=model.title,
            messages=messages,
            memory_summary=model.memory_summary,
            is_closed=model.is_closed,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_model(entity: Conversation) -> ConversationModel:
        return ConversationModel(
            id=entity.id,
            dataset_id=entity.dataset_id,
            title=entity.title,
            messages=[m.to_dict() for m in entity.messages],
            memory_summary=entity.memory_summary,
            message_count=entity.message_count,
            is_closed=entity.is_closed,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    @staticmethod
    def _update_model(model: ConversationModel, entity: Conversation) -> None:
        model.title = entity.title
        model.messages = [m.to_dict() for m in entity.messages]
        model.memory_summary = entity.memory_summary
        model.message_count = entity.message_count
        model.is_closed = entity.is_closed
        model.updated_at = entity.updated_at or datetime.now(UTC)
