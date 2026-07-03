"""ValueObject — base class for DDD value objects.

Value objects have no identity of their own. Two value objects are equal
if all their attributes are equal. They must be immutable — any change
produces a new instance rather than mutating the existing one.

Examples in this codebase:
    DatasetId, MimeType, SemanticType, SessionId, CorrelationCoefficient
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValueObject:
    """Immutable base class for all value objects.

    Subclasses should:
    1. Declare all attributes as dataclass fields (they become constructor params).
    2. Override ``_validate`` to enforce invariants — it is called automatically
       after ``__init__`` via ``__post_init__``.
    3. Add domain-specific properties for derived values or type checks.

    Example::

        @dataclass(frozen=True)
        class DatasetId(ValueObject):
            value: str

            def _validate(self) -> None:
                try:
                    uuid.UUID(self.value)
                except ValueError:
                    raise ValueError(f"DatasetId must be a valid UUID, got: {self.value!r}")

            def __str__(self) -> str:
                return self.value
    """

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        """Override in subclasses to enforce domain invariants.

        Raise ``ValueError`` or a domain-specific exception if the
        value is invalid. Called once during construction.
        """

    def equals(self, other: object) -> bool:
        """Explicit equality check — mirrors ``__eq__`` for readability in tests."""
        return self == other
