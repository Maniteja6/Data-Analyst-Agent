"""Base DomainEvent — every domain event in the system inherits from this.

Events are immutable value objects that record something that happened
in the domain. They are collected on aggregate roots and flushed to the
event bus (Kafka) after the aggregate is persisted.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class DomainEvent:
    """Immutable base class for all domain events.

    Attributes:
        event_id:       Unique identifier for this specific event occurrence.
        correlation_id: Ties related events across bounded contexts together
                        (e.g. all events triggered by one upload share a correlation_id).
        causation_id:   ID of the event or command that caused this event.
                        Enables causal chain tracing in distributed traces.
        occurred_at:    UTC timestamp of when the event occurred.
    """

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    causation_id: str | None = None
    occurred_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def event_type(self) -> str:
        """Returns the class name as the event type string.

        Used by the Kafka event bus to route events to the correct topic
        via EVENT_TOPIC_MAP in kafka_event_bus.py.
        """
        return self.__class__.__name__

    def to_dict(self) -> dict:
        """Serialises the event to a dict for Kafka / JSON transport."""
        return {
            "event_id":       self.event_id,
            "event_type":     self.event_type,
            "correlation_id": self.correlation_id,
            "causation_id":   self.causation_id,
            "occurred_at":    self.occurred_at.isoformat(),
        }

    def with_correlation(self, correlation_id: str, causation_id: str | None = None) -> "DomainEvent":
        """Return a copy of the event with the given correlation/causation IDs.

        Used when propagating context from a parent command or event.
        Because the dataclass is frozen, we create a new instance via object.__new__.
        """
        import copy
        new = copy.copy(self)
        # Frozen dataclasses don't allow setattr; bypass via object.__setattr__
        object.__setattr__(new, "correlation_id", correlation_id)
        if causation_id is not None:
            object.__setattr__(new, "causation_id", causation_id)
        return new
