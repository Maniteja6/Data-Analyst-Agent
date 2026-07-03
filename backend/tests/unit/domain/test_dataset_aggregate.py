"""Unit tests for the Dataset aggregate root."""
import pytest
from backend.domain.dataset.entities.dataset import Dataset
from backend.domain.dataset.value_objects.dataset_status import DatasetStatus
from backend.domain.dataset.exceptions import InvalidStatusTransitionError, DuplicateDatasetError


@pytest.mark.unit
class TestDatasetAggregate:

    def test_create_emits_dataset_uploaded_event(self, fake_dataset):
        # Events are consumed in fixture; create a fresh one
        ds = Dataset.create(
            id="test-id", project_id=None, original_name="test.csv",
            storage_key="datasets/test-id/test.csv", size_bytes=100, mime_type="text/csv",
        )
        events = ds.pull_domain_events()
        assert len(events) == 1
        assert events[0].event_type == "DatasetUploaded"

    def test_initial_status_is_uploaded(self, fake_dataset):
        assert fake_dataset.status == DatasetStatus.UPLOADED

    def test_begin_profiling_transitions_status(self, fake_dataset):
        fake_dataset.begin_profiling()
        assert fake_dataset.status == DatasetStatus.PROFILING

    def test_invalid_transition_raises(self, fake_dataset):
        with pytest.raises(InvalidStatusTransitionError):
            fake_dataset.mark_ready(row_count=100, column_count=5)   # can't skip to READY

    def test_full_pipeline_state_machine(self):
        ds = Dataset.create(
            id="x", project_id=None, original_name="f.csv",
            storage_key="s", size_bytes=10, mime_type="text/csv",
        )
        ds.pull_domain_events()
        ds.begin_profiling()
        ds.complete_profiling()
        ds.begin_cleaning()
        ds.mark_ready(row_count=100, column_count=5)

        events = ds.pull_domain_events()
        assert ds.status == DatasetStatus.READY
        assert any(e.event_type == "DatasetReady" for e in events)

    def test_mark_failed_from_any_state(self):
        ds = Dataset.create(
            id="y", project_id=None, original_name="f.csv",
            storage_key="s", size_bytes=10, mime_type="text/csv",
        )
        ds.pull_domain_events()
        ds.begin_profiling()
        ds.mark_failed("S3 connection error")

        assert ds.status    == DatasetStatus.FAILED
        assert "S3"         in ds.error_message
        events = ds.pull_domain_events()
        assert any(e.event_type == "DatasetFailed" for e in events)

    def test_has_time_series_false_without_schema(self, fake_dataset):
        assert fake_dataset.has_time_series is False

    def test_has_schema_true_after_schema_set(self, fake_dataset):
        fake_dataset.schema_json = {"columns": [{"name": "date", "semantic_type": "datetime"}]}
        assert fake_dataset.has_schema is True
        assert fake_dataset.has_time_series is True
