"""IVectorStoreService — abstract port for RAG vector operations."""

from __future__ import annotations

from abc import ABC, abstractmethod


class IVectorStoreService(ABC):
    @abstractmethod
    async def index_dataset(
        self, dataset_id: str, profile: object, project_id: str = ""
    ) -> int: ...
    @abstractmethod
    async def delete_dataset_chunks(self, dataset_id: str) -> None: ...
    @abstractmethod
    async def search(
        self, query_vector: list[float], dataset_id: str, top_k: int = 8
    ) -> list[dict]: ...
    @abstractmethod
    async def ping(self) -> bool: ...
