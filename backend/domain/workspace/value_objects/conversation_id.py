"""ConversationId value object — typed UUID for Conversation aggregates."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from backend.shared.value_object import ValueObject


@dataclass(frozen=True)
class ConversationId(ValueObject):
    """Strongly-typed UUID wrapper for Conversation identity.

    Prevents accidentally passing a DatasetId or SessionId where a
    ConversationId is expected — the type checker catches it at compile time.

    Example::

        cid = ConversationId.generate()
        print(str(cid))  # '550e8400-e29b-41d4-a716-446655440000'

        # Raises ValueError:
        ConversationId(value="not-a-uuid")
    """

    value: str

    def _validate(self) -> None:
        try:
            uuid.UUID(self.value)
        except (ValueError, AttributeError) as exc:
            raise ValueError(
                f"ConversationId must be a valid UUID4 string, got: {self.value!r}"
            ) from exc

    @classmethod
    def generate(cls) -> ConversationId:
        """Factory — creates a new random ConversationId."""
        return cls(value=str(uuid.uuid4()))

    @classmethod
    def from_string(cls, value: str) -> ConversationId:
        """Parse and normalise a string into a ConversationId."""
        return cls(value=str(uuid.UUID(value)))

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"ConversationId('{self.value}')"
