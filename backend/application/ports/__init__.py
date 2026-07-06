"""Abstract port interfaces for infrastructure dependencies."""
"""Abstract port interfaces — the boundary between application and infrastructure.

All ports are ABCs; concrete implementations live in backend.infrastructure.
Injected at the composition root (backend.api.dependencies).

    IStorageService    — upload_fileobj, download_bytes, generate_presigned_url
    ICacheService      — get/set/get_json/set_json/publish_json/cache_job_status
    IEventBus          — publish(DomainEvent), publish_batch
    IJobService        — enqueue_analysis/agents/report, get_task_status
    ILLMService        — complete, converse, stream, embed
    IVectorStoreService— upsert, search, ensure_collection, delete_by_dataset
"""
from backend.application.ports.storage_port      import IStorageService
from backend.application.ports.cache_port        import ICacheService
from backend.application.ports.event_bus_port    import IEventBus
from backend.application.ports.job_port          import IJobService
from backend.application.ports.llm_port         import ILLMService
from backend.application.ports.vector_store_port import IVectorStoreService

__all__ = [
    "IStorageService", "ICacheService", "IEventBus",
    "IJobService", "ILLMService", "IVectorStoreService",
]
