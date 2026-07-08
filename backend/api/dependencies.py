"""FastAPI dependency injection factories.

All use cases and services are constructed here and injected via FastAPI's
``Depends()`` system. This module is the composition root — it is the only
place that imports concrete infrastructure adapters, keeping the domain and
application layers free of infrastructure dependencies.

Usage in routers::

    @router.post("/datasets/upload")
    async def upload_dataset(
        use_case: UploadDatasetUseCase = Depends(get_upload_use_case),
        db: AsyncSession              = Depends(get_db_session),
    ):
        ...
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.infrastructure.persistence.database import get_db_session
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from backend.application.use_cases.create_conversation import CreateConversationUseCase
    from backend.application.use_cases.export_report import ExportReportUseCase
    from backend.application.use_cases.get_dataset import GetDatasetUseCase
    from backend.application.use_cases.get_insights import GetInsightsUseCase
    from backend.application.use_cases.get_job_status import GetJobStatusUseCase
    from backend.application.use_cases.run_analysis import RunAnalysisUseCase
    from backend.application.use_cases.send_message import SendMessageUseCase
    from backend.application.use_cases.upload_dataset import UploadDatasetUseCase
    from backend.domain.analytics.repositories.session_repository import SessionRepository
    from backend.domain.dataset.repositories.dataset_repository import DatasetRepository
    from backend.domain.insight.repositories.insight_repository import InsightRepository
    from backend.domain.workspace.repositories.conversation_repository import (
        ConversationRepository,
    )
    from backend.infrastructure.cache.redis_cache_adapter import RedisCacheAdapter
    from backend.infrastructure.job_queue.celery_job_adapter import CeleryJobAdapter
    from backend.infrastructure.llm.llm_port import ILLMService
    from backend.infrastructure.messaging.kafka_event_bus import KafkaEventBus
    from backend.infrastructure.storage.local_storage_adapter import LocalStorageAdapter
    from backend.infrastructure.storage.s3_storage_adapter import S3StorageAdapter

# ---------------------------------------------------------------------------
# Infrastructure singletons (created once per worker process)
# ---------------------------------------------------------------------------


def get_cache() -> RedisCacheAdapter:
    from backend.infrastructure.cache.redis_cache_adapter import get_redis_cache

    return get_redis_cache()


def get_storage() -> LocalStorageAdapter | S3StorageAdapter:
    from backend.config.settings import get_settings

    settings = get_settings()
    if settings.s3_endpoint_url == "local://":
        from backend.infrastructure.storage.local_storage_adapter import LocalStorageAdapter

        return LocalStorageAdapter()
    from backend.infrastructure.storage.s3_storage_adapter import get_s3_storage

    return get_s3_storage()


def get_event_bus() -> KafkaEventBus:
    from backend.config.feature_flags import flags

    if flags.kafka_enabled:
        from backend.infrastructure.messaging.kafka_event_bus import KafkaEventBus

        return KafkaEventBus()
    from backend.infrastructure.messaging.kafka_event_bus import KafkaEventBus

    return KafkaEventBus()  # still returns but publish is no-op when not started


def get_job_service() -> CeleryJobAdapter:
    from backend.infrastructure.job_queue.celery_job_adapter import CeleryJobAdapter

    return CeleryJobAdapter()


def get_llm_service() -> ILLMService:
    from backend.config.settings import get_settings

    settings = get_settings()
    if settings.app_env == "test":
        from backend.infrastructure.llm.llm_port import MockLLMService

        return MockLLMService()
    from backend.infrastructure.llm.llm_port import BedrockLLMService

    return BedrockLLMService()


# ---------------------------------------------------------------------------
# Repository factories (scoped to the request's DB session)
# ---------------------------------------------------------------------------


def get_dataset_repo(db: AsyncSession = Depends(get_db_session)) -> DatasetRepository:
    from backend.infrastructure.persistence.repositories.postgres_dataset_repository import (
        PostgresDatasetRepository,
    )

    return PostgresDatasetRepository(db)


def get_session_repo(db: AsyncSession = Depends(get_db_session)) -> SessionRepository:
    from backend.infrastructure.persistence.repositories.postgres_session_repository import (
        PostgresSessionRepository,
    )

    return PostgresSessionRepository(db)


def get_insight_repo(db: AsyncSession = Depends(get_db_session)) -> InsightRepository:
    from backend.infrastructure.persistence.repositories.postgres_insight_repository import (
        PostgresInsightRepository,
    )

    return PostgresInsightRepository(db)


def get_conversation_repo(db: AsyncSession = Depends(get_db_session)) -> ConversationRepository:
    from backend.infrastructure.persistence.repositories.postgres_conversation_repository import (
        PostgresConversationRepository,
    )

    return PostgresConversationRepository(db)


# ---------------------------------------------------------------------------
# Use case factories
# ---------------------------------------------------------------------------


def get_upload_use_case(
    dataset_repo: DatasetRepository = Depends(get_dataset_repo),
) -> UploadDatasetUseCase:
    from backend.application.use_cases.upload_dataset import UploadDatasetUseCase

    return UploadDatasetUseCase(
        storage=get_storage(),
        dataset_repo=dataset_repo,
        event_bus=get_event_bus(),
        job_service=get_job_service(),
    )


def get_run_analysis_use_case(
    dataset_repo: DatasetRepository = Depends(get_dataset_repo),
    session_repo: SessionRepository = Depends(get_session_repo),
) -> RunAnalysisUseCase:
    from backend.application.use_cases.run_analysis import RunAnalysisUseCase

    return RunAnalysisUseCase(
        dataset_repo=dataset_repo,
        session_repo=session_repo,
        job_service=get_job_service(),
    )


def get_get_dataset_use_case(
    dataset_repo: DatasetRepository = Depends(get_dataset_repo),
) -> GetDatasetUseCase:
    from backend.application.use_cases.get_dataset import GetDatasetUseCase

    return GetDatasetUseCase(dataset_repo=dataset_repo)


def get_get_insights_use_case(
    insight_repo: InsightRepository = Depends(get_insight_repo),
) -> GetInsightsUseCase:
    from backend.application.use_cases.get_insights import GetInsightsUseCase

    return GetInsightsUseCase(insight_repo=insight_repo, cache=get_cache())


def get_job_status_use_case() -> GetJobStatusUseCase:
    from backend.application.use_cases.get_job_status import GetJobStatusUseCase

    return GetJobStatusUseCase(cache=get_cache(), job_service=get_job_service())


def get_create_conversation_use_case(
    conversation_repo: ConversationRepository = Depends(get_conversation_repo),
    dataset_repo: DatasetRepository = Depends(get_dataset_repo),
) -> CreateConversationUseCase:
    from backend.application.use_cases.create_conversation import CreateConversationUseCase

    return CreateConversationUseCase(
        conversation_repo=conversation_repo,
        dataset_repo=dataset_repo,
    )


def get_send_message_use_case(
    conversation_repo: ConversationRepository = Depends(get_conversation_repo),
    dataset_repo: DatasetRepository = Depends(get_dataset_repo),
) -> SendMessageUseCase:
    from backend.application.use_cases.send_message import SendMessageUseCase

    return SendMessageUseCase(
        conversation_repo=conversation_repo,
        dataset_repo=dataset_repo,
        cache=get_cache(),
        llm_service=get_llm_service(),
    )


def get_export_report_use_case(
    insight_repo: InsightRepository = Depends(get_insight_repo),
) -> ExportReportUseCase:
    from backend.application.use_cases.export_report import ExportReportUseCase

    return ExportReportUseCase(
        insight_repo=insight_repo,
        job_service=get_job_service(),
        cache=get_cache(),
    )
