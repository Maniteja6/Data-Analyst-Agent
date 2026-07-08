"""ConversationCreated domain event."""

from __future__ import annotations

from dataclasses import dataclass

from backend.shared.domain_event import DomainEvent


@dataclass(frozen=True)
class ConversationCreated(DomainEvent):
    """Emitted by ``Conversation.create()`` when a new chat session starts.

    Consumed by:
    - WebSocket gateway — joins the client to the conversation's room
    - Audit logger — records conversation creation for the workspace history
    """

    conversation_id: str = ""
    dataset_id: str = ""
    title: str = ""

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update(
            {
                "conversation_id": self.conversation_id,
                "dataset_id": self.dataset_id,
                "title": self.title,
            }
        )
        return base
