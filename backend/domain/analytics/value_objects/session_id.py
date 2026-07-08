"""SessionId value object — typed UUID for analysis sessions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from backend.shared.value_object import ValueObject


@dataclass(frozen=True)
class SessionId(ValueObject):
    """Unique identifier for an AnalysisSession.

    Separate from DatasetId so that the same dataset can have multiple
    analysis sessions (e.g. after the user re-uploads a corrected file
    or triggers a re-analysis with different agent parameters).
    """

    value: str

    def _validate(self) -> None:
        try:
            uuid.UUID(self.value)
        except (ValueError, AttributeError) as exc:
            raise ValueError(f"SessionId must be a valid UUID, got: {self.value!r}") from exc

    @classmethod
    def generate(cls) -> SessionId:
        """Factory — creates a new random SessionId."""
        return cls(value=str(uuid.uuid4()))

    def __str__(self) -> str:
        return self.value
