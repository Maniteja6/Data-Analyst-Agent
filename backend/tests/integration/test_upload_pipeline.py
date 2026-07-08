"""Integration test: dataset upload → status → delete."""

import io

import pytest


@pytest.mark.integration
class TestUploadPipeline:
    @pytest.mark.asyncio
    async def test_upload_returns_dataset_id_and_job_id(
        self, local_storage, in_memory_cache, null_job_service
    ) -> None:
        """UploadDatasetUseCase should persist to in-memory repo and return IDs."""
        from backend.application.commands.upload_dataset_command import UploadDatasetCommand
        from backend.application.use_cases.upload_dataset import UploadDatasetUseCase
        from backend.infrastructure.messaging.kafka_event_bus import KafkaEventBus

        class _FakeRepo:
            saved = []

            async def get_by_checksum(self, c) -> None:
                return None

            async def save(self, entity):
                self.saved.append(entity)
                return entity

        repo = _FakeRepo()
        bus = KafkaEventBus()  # won't connect without a broker
        use_case = UploadDatasetUseCase(
            storage=local_storage,
            dataset_repo=repo,
            event_bus=bus,
            job_service=null_job_service,
        )

        csv_data = b"col_a,col_b\n1,hello\n2,world\n"
        cmd = UploadDatasetCommand(
            filename="test.csv",
            file_obj=io.BytesIO(csv_data),
            size_bytes=len(csv_data),
            mime_type="text/csv",
            project_id=None,
            correlation_id="test-corr-id",
        )
        result = await use_case.execute(cmd)

        assert "dataset_id" in result
        assert "job_id" in result
        assert result["status"] == "uploaded"
        assert len(repo.saved) == 1

    @pytest.mark.asyncio
    async def test_duplicate_upload_raises(self, local_storage, null_job_service) -> None:
        from backend.application.commands.upload_dataset_command import UploadDatasetCommand
        from backend.application.use_cases.upload_dataset import UploadDatasetUseCase
        from backend.domain.dataset.entities.dataset import Dataset
        from backend.domain.dataset.exceptions import DuplicateDatasetError
        from backend.infrastructure.messaging.kafka_event_bus import KafkaEventBus

        existing_checksum = "a" * 64

        class _FakeRepo:
            async def get_by_checksum(self, c):
                return Dataset.create(
                    id="existing-id",
                    project_id=None,
                    original_name="old.csv",
                    storage_key="s",
                    size_bytes=10,
                    mime_type="text/csv",
                    checksum_sha256=existing_checksum,
                )

            async def save(self, entity):
                return entity

        use_case = UploadDatasetUseCase(
            storage=local_storage,
            dataset_repo=_FakeRepo(),
            event_bus=KafkaEventBus(),
            job_service=null_job_service,
        )
        csv_data = b"col_a,col_b\n1,hello\n"
        cmd = UploadDatasetCommand(
            filename="dup.csv",
            file_obj=io.BytesIO(csv_data),
            size_bytes=len(csv_data),
            mime_type="text/csv",
        )
        with pytest.raises(DuplicateDatasetError):
            await use_case.execute(cmd)
