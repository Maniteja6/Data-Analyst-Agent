"""Entity — base class for DDD entities.

Entities have a unique identity that persists across state changes.
Two entities are equal if and only if their IDs are equal, regardless
of the values of their other attributes.

Unlike value objects, entities are mutable — their attributes change
over time while their identity remains constant.

Examples in this codebase:
    ColumnSchema, FileMetadata, AnalysisSession, AnomalyAlert, Message
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class Entity:
    """Base class for entities with UUID identity.

    Subclasses should declare additional fields using ``@dataclass``
    and call ``super().__init__()`` if they define ``__init__`` manually.

    Example::

        @dataclass
        class ColumnSchema(Entity):
            name: str
            data_type: str
            semantic_type: SemanticType = SemanticType.UNKNOWN

        col = ColumnSchema(name="revenue", data_type="Float64")
        assert col.id  # auto-generated UUID string
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()), kw_only=True)

    # ------------------------------------------------------------------
    # Identity-based equality
    # ------------------------------------------------------------------

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash((self.__class__.__name__, self.id))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.id!r})"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def is_same_entity(self, other: Entity) -> bool:
        """Explicit identity check — clearer than ``==`` in domain methods."""
        return self.__class__ is other.__class__ and self.id == other.id
