"""Repository — abstract base interface for all data repositories.

Repositories decouple the domain model from persistence details.
The domain layer declares what it needs (this interface); the
infrastructure layer provides the implementation (e.g. PostgresDatasetRepository).

This follows the Dependency Inversion Principle: high-level use cases
depend on the abstract ``Repository``, not on SQLAlchemy or any other ORM.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

# Define TypeVars explicitly for 3.11 compatibility
T = TypeVar("T")
ID = TypeVar("ID")


class Repository(Generic[T, ID], ABC):
    """Generic CRUD repository contract.

    All concrete repository implementations must live in the infrastructure
    layer and accept a database session via their constructor so that the
    unit-of-work pattern (session commit/rollback) stays under use-case control.

    Example concrete implementation::

        class PostgresDatasetRepository(DatasetRepository):
            def __init__(self, session: AsyncSession) -> None:
                self._session = session

            async def get_by_id(self, entity_id: str) -> Dataset | None:
                result = await self._session.execute(
                    select(DatasetModel).where(DatasetModel.id == entity_id)
                )
                model = result.scalar_one_or_none()
                return _to_domain(model) if model else None
    """

    @abstractmethod
    async def get_by_id(self, entity_id: ID) -> T | None:
        """Retrieve a single entity by its unique identifier.

        Returns ``None`` if the entity does not exist (callers that
        require existence should raise ``NotFoundError`` themselves).
        """

    @abstractmethod
    async def save(self, entity: T) -> T:
        """Persist a new or updated entity.

        Implementations must be idempotent — calling ``save`` on an
        already-persisted entity with the same ID updates it in place.
        Returns the saved entity (may differ if the DB enriches it,
        e.g. via server-generated timestamps).
        """

    @abstractmethod
    async def delete(self, entity_id: ID) -> None:
        """Soft- or hard-delete an entity by ID.

        Implementations should prefer soft-delete (setting ``deleted_at``)
        over hard-delete to support audit trails and recovery.
        """


class ReadOnlyRepository(Generic[T, ID], ABC):
    """Read-only variant — used for query-side repositories that never mutate state."""

    @abstractmethod
    async def get_by_id(self, entity_id: ID) -> T | None: ...

    @abstractmethod
    async def list_all(self) -> list[T]: ...
