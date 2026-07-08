"""UploadDatasetUseCase — handles dataset file upload end-to-end."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import structlog
from backend.application.commands.upload_dataset_command import UploadDatasetCommand
from backend.domain.dataset.entities.dataset import Dataset
from backend.domain.dataset.exceptions import DuplicateDatasetError
from backend.domain.dataset.services.dataset_service import DatasetService
from backend.shared.utils.uuid_factory import new_uuid

if TYPE_CHECKING:
    from backend.domain.dataset.repositories.dataset_repository import DatasetRepository
    from backend.infrastructure.job_queue.celery_job_adapter import CeleryJobAdapter
    from backend.infrastructure.messaging.kafka_event_bus import KafkaEventBus
    from backend.infrastructure.storage.local_storage_adapter import LocalStorageAdapter
    from backend.infrastructure.storage.s3_storage_adapter import S3StorageAdapter

logger = structlog.get_logger(__name__)


class UploadDatasetUseCase:
    """Validates, stores, and registers a new dataset, then enqueues analysis.

    Steps:
      1. Validate filename and size via DatasetService
      2. Compute SHA-256 checksum for deduplication
      3. Check for duplicate upload
      4. Upload file to S3/local storage
      5. Create Dataset aggregate and persist to Postgres
      6. Publish DatasetUploaded domain event
      7. Enqueue Celery analysis pipeline task
      8. Return the new dataset_id and job_id
    """

    def __init__(
        self,
        storage: LocalStorageAdapter | S3StorageAdapter,
        dataset_repo: DatasetRepository,
        event_bus: KafkaEventBus,
        job_service: CeleryJobAdapter,
        dataset_service: DatasetService | None = None,
    ) -> None:
        self._storage = storage
        self._repo = dataset_repo
        self._event_bus = event_bus
        self._job_service = job_service
        self._dataset_service = dataset_service or DatasetService()

    async def execute(self, cmd: UploadDatasetCommand) -> dict:
        """Execute the upload use case.

        Returns:
            ``{'dataset_id': str, 'job_id': str, 'status': 'uploaded'}``
        """
        # Step 1: Validate
        self._dataset_service.validate_file(cmd.filename, cmd.size_bytes)
        mime_type = self._dataset_service.infer_mime_from_extension(cmd.filename)

        # Step 2: Checksum
        dataset_id = new_uuid()
        checksum = await self._compute_checksum(cmd)

        # Step 3: Deduplication check
        existing = await self._repo.get_by_checksum(checksum)
        if existing:
            raise DuplicateDatasetError(checksum, existing.id)

        # Step 4: Upload to storage
        storage_key = self._dataset_service.build_storage_key(dataset_id, cmd.filename)
        await self._storage.upload_fileobj(cmd.file_obj, storage_key, content_type=mime_type)
        logger.info("dataset_file_uploaded", key=storage_key, size=cmd.size_bytes)

        # Step 5: Create and persist aggregate
        dataset = Dataset.create(
            id=dataset_id,
            project_id=cmd.project_id,
            original_name=cmd.filename,
            storage_key=storage_key,
            size_bytes=cmd.size_bytes,
            mime_type=mime_type,
            checksum_sha256=checksum,
        )
        await self._repo.save(dataset)

        # Step 6: Publish domain events
        for event in dataset.pull_domain_events():
            await self._event_bus.publish(event, partition_key=dataset_id)

        # Step 7: Enqueue analysis pipeline
        job_id = self._job_service.enqueue_analysis(
            dataset_id=dataset_id,
            storage_key=storage_key,
            correlation_id=cmd.correlation_id,
        )
        logger.info(
            "upload_complete",
            dataset_id=dataset_id,
            job_id=job_id,
            filename=cmd.filename,
        )
        return {"dataset_id": dataset_id, "job_id": job_id, "status": "uploaded"}

    @staticmethod
    async def _compute_checksum(cmd: UploadDatasetCommand) -> str:
        """Compute SHA-256 of the file bytes without re-reading the full stream."""
        import asyncio

        loop = asyncio.get_event_loop()

        def _hash() -> str:
            sha = hashlib.sha256()
            cmd.file_obj.seek(0)
            for chunk in iter(lambda: cmd.file_obj.read(8192), b""):
                sha.update(chunk)
            cmd.file_obj.seek(0)  # rewind for the upload step
            return sha.hexdigest()

        return await loop.run_in_executor(None, _hash)
