"""CreateConversationUseCase — creates a new chat conversation for a dataset."""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.domain.dataset.exceptions import DatasetNotFoundError
from backend.domain.workspace.entities.conversation import Conversation
from backend.shared.utils.uuid_factory import new_uuid

if TYPE_CHECKING:
    from backend.domain.dataset.repositories.dataset_repository import DatasetRepository
    from backend.domain.workspace.repositories.conversation_repository import (
        ConversationRepository,
    )


class CreateConversationUseCase:
    def __init__(
        self, conversation_repo: ConversationRepository, dataset_repo: DatasetRepository
    ) -> None:
        self._conv_repo = conversation_repo
        self._dataset_repo = dataset_repo

    async def execute(self, dataset_id: str, title: str = "") -> dict:
        dataset = await self._dataset_repo.get_by_id(dataset_id)
        if dataset is None:
            raise DatasetNotFoundError(dataset_id)

        conversation = Conversation.create(
            conversation_id=new_uuid(),
            dataset_id=dataset_id,
            title=title or f"Chat about {dataset.original_name}",
        )
        await self._conv_repo.save(conversation)
        return {
            "conversation_id": conversation.id,
            "dataset_id": dataset_id,
            "title": conversation.title,
            "created_at": conversation.created_at.isoformat() if conversation.created_at else None,
        }
