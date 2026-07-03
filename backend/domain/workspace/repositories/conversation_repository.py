"""ConversationRepository — abstract port for Conversation aggregate persistence."""
from __future__ import annotations

from abc import abstractmethod

from backend.shared.repository import Repository
from backend.domain.workspace.entities.conversation import Conversation


class ConversationRepository(Repository[Conversation, str]):
    """Abstract repository for Conversation aggregates.

    Concrete implementation:
    ``backend/infrastructure/persistence/repositories/postgres_conversation_repository.py``

    Message bodies are stored as JSONB on the conversation row for fast
    retrieval. The ``messages`` JSONB column is append-only in practice —
    a DB trigger enforces this in production.
    """

    @abstractmethod
    async def get_by_id(self, entity_id: str) -> Conversation | None:
        """Return a Conversation (with all its Messages) by UUID, or None."""

    @abstractmethod
    async def save(self, entity: Conversation) -> Conversation:
        """Insert or update a Conversation and its message list."""

    @abstractmethod
    async def delete(self, entity_id: str) -> None:
        """Soft-delete a Conversation (GDPR erasure — also wipes message content)."""

    @abstractmethod
    async def get_by_dataset_id(self, dataset_id: str) -> list[Conversation]:
        """Return all non-deleted conversations about a dataset, newest first.

        Used to populate the sidebar conversation list and to find the
        most recent conversation to resume when the user revisits a dataset.
        """

    @abstractmethod
    async def get_by_project_id(self, project_id: str) -> list[Conversation]:
        """Return all non-deleted conversations for a project."""

    @abstractmethod
    async def get_active_by_dataset_id(self, dataset_id: str) -> Conversation | None:
        """Return the most recent non-closed conversation for a dataset.

        Used by the frontend to auto-resume the last session when the user
        returns to a dataset rather than always creating a new conversation.
        """

    @abstractmethod
    async def count_by_dataset(self, dataset_id: str) -> int:
        """Count conversations for a dataset — used for pagination."""

    @abstractmethod
    async def search_by_content(
        self, dataset_id: str, query: str, limit: int = 10
    ) -> list[Conversation]:
        """Full-text search over message content within a dataset's conversations.

        Implemented via PostgreSQL ``tsvector`` or a simple ``ILIKE`` scan.
        Used by the search-past-chats feature flag.
        """
