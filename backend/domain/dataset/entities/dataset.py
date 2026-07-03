"""Dataset aggregate root — the central entity of the dataset bounded context."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.shared.aggregate_root import AggregateRoot
from backend.domain.dataset.value_objects.dataset_status import DatasetStatus
from backend.domain.dataset.value_objects.semantic_type import SemanticType
from backend.domain.dataset.events.dataset_uploaded import DatasetUploaded
from backend.domain.dataset.events.dataset_ready import DatasetReady
from backend.domain.dataset.events.dataset_failed import DatasetFailed
from backend.domain.dataset.events.schema_inferred import SchemaInferred
from backend.domain.dataset.exceptions import InvalidStatusTransitionError


# Valid state machine transitions
_TRANSITIONS: dict[DatasetStatus, set[DatasetStatus]] = {
    DatasetStatus.UPLOADED:  {DatasetStatus.PROFILING, DatasetStatus.FAILED},
    DatasetStatus.PROFILING: {DatasetStatus.PROFILED,  DatasetStatus.FAILED},
    DatasetStatus.PROFILED:  {DatasetStatus.CLEANING,  DatasetStatus.FAILED},
    DatasetStatus.CLEANING:  {DatasetStatus.READY,     DatasetStatus.FAILED},
    DatasetStatus.READY:     set(),
    DatasetStatus.FAILED:    set(),
}


@dataclass
class Dataset(AggregateRoot):
    """Dataset aggregate root — owns the upload-to-ready lifecycle.

    The Dataset is the primary aggregate in the system. Every other
    bounded context (analytics, insight, workspace) references datasets
    by their ID but does not own them.

    State machine overview:
        UPLOADED → PROFILING → PROFILED → CLEANING → READY
                                    ↘ FAILED (from any state)

    Domain events emitted during state transitions flow to:
    - Kafka topics (consumed by the analytics pipeline workers)
    - WebSocket rooms (consumed by the browser for real-time progress)

    Attributes:
        id:               Dataset UUID.
        project_id:       Optional workspace project this dataset belongs to.
        original_name:    User-supplied filename (e.g. ``'sales_q3.csv'``).
        storage_key:      S3/MinIO object key for the raw file bytes.
        size_bytes:       File size at upload time.
        mime_type:        Validated MIME type string.
        status:           Current lifecycle state.
        row_count:        Populated after profiling completes.
        column_count:     Populated after profiling completes.
        checksum_sha256:  SHA-256 of raw bytes — used for deduplication.
        schema_json:      Column schema dict populated after schema inference.
        error_message:    Set when status transitions to FAILED.
        created_at:       UTC timestamp of initial upload.
        updated_at:       UTC timestamp of last status change.
    """

    id:               str
    project_id:       str | None
    original_name:    str
    storage_key:      str
    size_bytes:       int
    mime_type:        str
    status:           DatasetStatus    = DatasetStatus.UPLOADED
    row_count:        int | None       = None
    column_count:     int | None       = None
    checksum_sha256:  str | None       = None
    schema_json:      dict | None      = None
    error_message:    str | None       = None
    created_at:       datetime | None  = None
    updated_at:       datetime | None  = None

    def __post_init__(self) -> None:
        super().__init__()

    # ── State machine ─────────────────────────────────────────────────────

    def _transition(self, target: DatasetStatus) -> None:
        """Enforce valid transitions. Raises InvalidStatusTransitionError otherwise."""
        allowed = _TRANSITIONS.get(self.status, set())
        if target not in allowed:
            raise InvalidStatusTransitionError(self.status, target)
        self.status     = target
        self.updated_at = datetime.now(timezone.utc)

    # ── Domain methods ────────────────────────────────────────────────────

    def begin_profiling(self) -> None:
        """Called when the analytics worker picks up the dataset for profiling."""
        self._transition(DatasetStatus.PROFILING)

    def complete_schema_inference(
        self,
        columns: list[dict],
        row_count: int,
        column_count: int,
    ) -> None:
        """Called when the Schema Agent finishes inferring column types.

        Populates ``schema_json`` and emits ``SchemaInferred``.
        Does not change the overall status — schema inference is a
        sub-step inside the PROFILING stage.

        Args:
            columns:      List of column dicts from ``ColumnSchema.to_dict()``.
            row_count:    Row count sampled during schema inference.
            column_count: Number of columns found in the dataset.
        """
        self.schema_json  = {"columns": columns, "column_count": column_count}
        self.row_count    = row_count
        self.column_count = column_count
        self.updated_at   = datetime.now(timezone.utc)
        self._record_event(SchemaInferred(
            dataset_id=self.id,
            column_count=column_count,
            row_count=row_count,
        ))

    def complete_profiling(self) -> None:
        """Called after DataProfiler finishes. Transitions to PROFILED."""
        self._transition(DatasetStatus.PROFILED)

    def begin_cleaning(self) -> None:
        """Called when the DataCleaner worker starts."""
        self._transition(DatasetStatus.CLEANING)

    def mark_ready(self, row_count: int, column_count: int, schema: dict | None = None) -> None:
        """Transitions to READY. Final success state. Emits DatasetReady.

        Args:
            row_count:    Final row count after cleaning (duplicates removed).
            column_count: Final column count after dropping high-null columns.
            schema:       Optional updated schema_json if cleaning changed types.
        """
        self._transition(DatasetStatus.READY)
        self.row_count    = row_count
        self.column_count = column_count
        if schema:
            self.schema_json = schema
        self._record_event(DatasetReady(dataset_id=self.id))

    def mark_failed(self, reason: str) -> None:
        """Transitions to FAILED from any non-terminal state. Emits DatasetFailed.

        Args:
            reason: Human-readable failure description stored in ``error_message``
                    and surfaced to the user on the upload progress component.
        """
        self._transition(DatasetStatus.FAILED)
        self.error_message = reason
        self._record_event(DatasetFailed(dataset_id=self.id, reason=reason))

    # ── Derived helpers ───────────────────────────────────────────────────

    @property
    def is_ready(self) -> bool:
        return self.status == DatasetStatus.READY

    @property
    def is_failed(self) -> bool:
        return self.status == DatasetStatus.FAILED

    @property
    def is_processing(self) -> bool:
        return self.status.is_processing

    @property
    def has_schema(self) -> bool:
        return self.schema_json is not None and bool(self.schema_json.get("columns"))

    @property
    def has_time_series(self) -> bool:
        """True when the schema contains at least one datetime/date column.
        Used to decide whether to show the Forecast panel in the frontend.
        """
        if not self.has_schema:
            return False
        return any(
            col.get("semantic_type") in (SemanticType.DATE.value, SemanticType.DATETIME.value)
            for col in self.schema_json["columns"]
        )

    @property
    def size_mb(self) -> float:
        return round(self.size_bytes / (1024 ** 2), 2)

    # ── Factory ───────────────────────────────────────────────────────────

    @classmethod
    def create(
        cls,
        *,
        id: str,
        project_id: str | None,
        original_name: str,
        storage_key: str,
        size_bytes: int,
        mime_type: str,
        checksum_sha256: str | None = None,
    ) -> "Dataset":
        """Factory method — creates a new Dataset in UPLOADED state.

        Emits ``DatasetUploaded`` so the Kafka consumer can trigger the
        analytics pipeline without the use case needing to know about Kafka.

        All creation must go through this factory to ensure the event is
        always emitted when a new dataset is persisted.
        """
        now = datetime.now(timezone.utc)
        dataset = cls(
            id=id,
            project_id=project_id,
            original_name=original_name,
            storage_key=storage_key,
            size_bytes=size_bytes,
            mime_type=mime_type,
            checksum_sha256=checksum_sha256,
            status=DatasetStatus.UPLOADED,
            created_at=now,
            updated_at=now,
        )
        dataset._record_event(DatasetUploaded(
            dataset_id=id,
            storage_key=storage_key,
            filename=original_name,
            size_bytes=size_bytes,
            mime_type=mime_type,
        ))
        return dataset
