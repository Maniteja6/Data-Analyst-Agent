"""AggregateRoot — base class for DDD aggregate roots.

An aggregate root is the single entry point to an aggregate cluster.
It enforces invariants for the whole cluster and is the only object
that other parts of the system may hold a direct reference to.

Domain events are recorded internally during state transitions and
flushed to the event bus after the aggregate is saved to the database,
ensuring events are only published for durable changes.
"""

from __future__ import annotations

from backend.shared.domain_event import DomainEvent


class AggregateRoot:
    """Collects domain events during aggregate state transitions.

    Usage::

        class Dataset(AggregateRoot):
            def mark_ready(self) -> None:
                self.status = DatasetStatus.READY
                self._record_event(DatasetReady(dataset_id=self.id))

        # In the use case / repository layer:
        dataset.mark_ready()
        await repo.save(dataset)
        for event in dataset.pull_domain_events():
            await event_bus.publish(event)
    """

    def __init__(self) -> None:
        self._domain_events: list[DomainEvent] = []

    # ------------------------------------------------------------------
    # Event recording
    # ------------------------------------------------------------------

    def _record_event(self, event: DomainEvent) -> None:
        """Append a domain event to the internal queue.

        Called by aggregate methods whenever a meaningful state change
        occurs that other bounded contexts need to react to.
        """
        self._domain_events.append(event)

    def pull_domain_events(self) -> list[DomainEvent]:
        """Return all queued events and clear the internal list.

        Should be called once, immediately after persisting the aggregate,
        before publishing to the event bus. Calling twice returns an empty
        list on the second call — events are consumed on first pull.
        """
        events = list(self._domain_events)
        self._domain_events.clear()
        return events

    def peek_domain_events(self) -> list[DomainEvent]:
        """Return queued events without consuming them (useful in tests)."""
        return list(self._domain_events)

    @property
    def has_domain_events(self) -> bool:
        """True if there are unpublished domain events in the queue."""
        return bool(self._domain_events)
