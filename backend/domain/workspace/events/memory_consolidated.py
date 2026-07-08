"""MemoryConsolidated domain event."""

from __future__ import annotations

from dataclasses import dataclass

from backend.shared.domain_event import DomainEvent


@dataclass(frozen=True)
class MemoryConsolidated(DomainEvent):
    """Emitted by ``Conversation.apply_memory_summary()`` after buffer compression.

    Kafka topic: ``chat.message`` (same topic; consumers inspect ``event_type``)

    Consumed by:
    - WebSocket gateway — optionally notifies the frontend that context was
      compressed (the UI may show a subtle "Context summarised" indicator
      so users understand why very early messages aren't directly visible)
    - Audit logger — records that user conversation data was compressed for
      privacy / GDPR compliance purposes

    Why emit this as an event rather than a synchronous call?
    Memory compression is triggered by the MemoryAgent when it detects
    ``needs_compression`` on the conversation. Emitting an event decouples
    the Conversation aggregate from the MemoryAgent implementation and
    allows the compression to be retried independently if it fails.

    Attributes:
        conversation_id:  UUID of the Conversation.
        dataset_id:       Associated dataset.
        turns_compressed: Number of message turns that were compressed.
        summary_preview:  First 80 characters of the memory summary.
    """

    conversation_id: str = ""
    dataset_id: str = ""
    turns_compressed: int = 0
    summary_preview: str = ""

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update(
            {
                "conversation_id": self.conversation_id,
                "dataset_id": self.dataset_id,
                "turns_compressed": self.turns_compressed,
                "summary_preview": self.summary_preview,
            }
        )
        return base
