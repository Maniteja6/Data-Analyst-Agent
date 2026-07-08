"""IJobService — abstract port for background job enqueueing."""

from __future__ import annotations

from abc import ABC, abstractmethod


class IJobService(ABC):
    @abstractmethod
    def enqueue_analysis(self, dataset_id: str, storage_key: str, correlation_id: str) -> str: ...
    @abstractmethod
    def enqueue_agents(self, dataset_id: str, session_id: str, correlation_id: str) -> str: ...
    @abstractmethod
    def enqueue_report(
        self, dataset_id: str, session_id: str, format: str, report_id: str | None = None
    ) -> str: ...
    @abstractmethod
    def get_task_status(self, task_id: str) -> dict: ...
    @abstractmethod
    def revoke_task(self, task_id: str, terminate: bool = False) -> None: ...
