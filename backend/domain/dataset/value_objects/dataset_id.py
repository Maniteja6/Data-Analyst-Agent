"""DatasetId value object — typed UUID identity for Dataset aggregates."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from backend.shared.value_object import ValueObject


@dataclass(frozen=True)
class DatasetId(ValueObject):
    """Strongly-typed UUID wrapper for Dataset identity.

    Using a dedicated value object instead of bare strings prevents
    accidentally passing a SessionId or ConversationId where a DatasetId
    is expected — the type checker catches the error at compile time.

    Example::

        dataset_id = DatasetId.generate()
        print(str(dataset_id))  # '550e8400-e29b-41d4-a716-446655440000'

        # Raises ValueError:
        DatasetId(value="not-a-uuid")
    """

    value: str

    def _validate(self) -> None:
        try:
            uuid.UUID(self.value)
        except (ValueError, AttributeError):
            raise ValueError(
                f"DatasetId must be a valid UUID4 string, got: {self.value!r}"
            )

    @classmethod
    def generate(cls) -> "DatasetId":
        """Factory — creates a new random DatasetId."""
        return cls(value=str(uuid.uuid4()))

    @classmethod
    def from_string(cls, value: str) -> "DatasetId":
        """Parse a string into a DatasetId, normalising to lowercase hyphenated form."""
        normalised = str(uuid.UUID(value))   # raises ValueError if invalid
        return cls(value=normalised)

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"DatasetId('{self.value}')"
