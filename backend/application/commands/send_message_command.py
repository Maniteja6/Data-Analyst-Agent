"""SendMessageCommand — input DTO for the SendMessageUseCase."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class SendMessageCommand:
    """A user chat message sent within an existing conversation.

    Attributes:
        conversation_id: UUID of the Conversation aggregate.
        dataset_id:      Dataset the conversation is about.
        content:         Raw text of the user's message.
        correlation_id:  Request-scoped tracing ID.
        stream:          When True, the use case should yield tokens
                         incrementally via the streaming LLM service.
    """
    conversation_id: str
    dataset_id:      str
    content:         str
    correlation_id:  str  = ""
    stream:          bool = False
