"""MessageAdded domain event."""
from __future__ import annotations

from dataclasses import dataclass

from backend.shared.domain_event import DomainEvent


@dataclass(frozen=True)
class MessageAdded(DomainEvent):
    """Emitted by ``Conversation.add_message()`` after each new turn.

    Kafka topic: ``chat.message``

    Consumed by:
    - WebSocket gateway — fan-out to all Socket.IO clients in the
      ``conversation:<id>`` room so every open browser tab sees the message
    - Audit logger — records message creation with role and content hash
      (content is hashed, not stored raw, to protect user privacy in logs)
    - MemoryAgent trigger — when ``needs_compression`` is True, the consumer
      enqueues a compression task so the next request finds a trimmed buffer

    Attributes:
        conversation_id: UUID of the Conversation aggregate.
        dataset_id:      Dataset the conversation is about.
        message_id:      UUID of the new Message entity.
        role:            ``'user'`` or ``'assistant'``.
        content_preview: First 100 characters of the message content,
                         for WebSocket notification display — NOT the full content.
    """

    conversation_id: str = ""
    dataset_id:      str = ""
    message_id:      str = ""
    role:            str = ""
    content_preview: str = ""

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({
            "conversation_id": self.conversation_id,
            "dataset_id":      self.dataset_id,
            "message_id":      self.message_id,
            "role":            self.role,
            "content_preview": self.content_preview,
        })
        return base
