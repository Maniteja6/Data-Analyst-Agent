"""IEventBus — abstract port for publishing domain events."""

from __future__ import annotations

from abc import ABC, abstractmethod

from backend.shared.domain_event import DomainEvent


class IEventBus(ABC):
    @abstractmethod
    async def publish(self, event: DomainEvent, partition_key: str | None = None) -> None: ...
    @abstractmethod
    async def publish_batch(
        self, events: list[DomainEvent], partition_key: str | None = None
    ) -> None: ...
    @abstractmethod
    async def ping(self) -> bool: ...
    @abstractmethod
    async def start(self) -> None: ...
    @abstractmethod
    async def stop(self) -> None: ...
