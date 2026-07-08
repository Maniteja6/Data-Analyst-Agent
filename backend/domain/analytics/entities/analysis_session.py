"""AnalysisSession aggregate root — orchestrates the analytics pipeline lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from backend.domain.analytics.entities.cleaning_report import CleaningReport
from backend.domain.analytics.entities.data_profile import DataProfile
from backend.domain.analytics.events.anomalies_detected import AnomaliesDetected
from backend.domain.analytics.events.cleaning_completed import CleaningCompleted
from backend.domain.analytics.events.profiling_completed import ProfilingCompleted
from backend.domain.analytics.exceptions import InvalidSessionStateError
from backend.shared.aggregate_root import AggregateRoot


class SessionStatus(str, Enum):
    PENDING = "pending"
    PROFILING = "profiling"
    PROFILED = "profiled"
    CLEANING = "cleaning"
    CLEANED = "cleaned"
    ANALYSING = "analysing"
    COMPLETE = "complete"
    FAILED = "failed"


_TRANSITIONS: dict[SessionStatus, set[SessionStatus]] = {
    SessionStatus.PENDING: {SessionStatus.PROFILING, SessionStatus.FAILED},
    SessionStatus.PROFILING: {SessionStatus.PROFILED, SessionStatus.FAILED},
    SessionStatus.PROFILED: {SessionStatus.CLEANING, SessionStatus.FAILED},
    SessionStatus.CLEANING: {SessionStatus.CLEANED, SessionStatus.FAILED},
    SessionStatus.CLEANED: {SessionStatus.ANALYSING, SessionStatus.FAILED},
    SessionStatus.ANALYSING: {SessionStatus.COMPLETE, SessionStatus.FAILED},
    SessionStatus.COMPLETE: set(),
    SessionStatus.FAILED: set(),
}


@dataclass
class AnalysisSession(AggregateRoot):
    """Aggregate root for one end-to-end dataset analysis run.

    Manages the state machine that tracks progress through:
    pending → profiling → profiled → cleaning → cleaned → analysing → complete

    Domain events are emitted at each state transition so downstream
    consumers (Kafka consumers, WebSocket gateway) can react in real time.

    Attributes:
        id:              Session UUID.
        dataset_id:      ID of the dataset being analysed.
        correlation_id:  Request-scoped tracing ID propagated from the upload.
        status:          Current state in the pipeline state machine.
        profile:         DataProfile populated after profiling completes.
        cleaning_report: CleaningReport populated after cleaning completes.
        anomaly_ids:     IDs of AnomalyAlert entities raised during analysis.
        error_message:   Populated if the session transitions to FAILED.
        started_at:      UTC timestamp when the session was created.
        completed_at:    UTC timestamp when status reached COMPLETE or FAILED.
    """

    id: str
    dataset_id: str
    correlation_id: str
    status: SessionStatus = SessionStatus.PENDING
    profile: DataProfile | None = None
    cleaning_report: CleaningReport | None = None
    anomaly_ids: list[str] = field(default_factory=list)
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        super().__init__()

    # ── State machine ─────────────────────────────────────────────────────

    def _transition(self, target: SessionStatus) -> None:
        allowed = _TRANSITIONS.get(self.status, set())
        if target not in allowed:
            raise InvalidSessionStateError(self.id, self.status.value, target.value)
        self.status = target

    # ── Pipeline callbacks ────────────────────────────────────────────────

    def begin_profiling(self) -> None:
        """Called when the profiling worker picks up the task."""
        self._transition(SessionStatus.PROFILING)
        if not self.started_at:
            self.started_at = datetime.now(UTC)

    def complete_profiling(self, profile: DataProfile) -> None:
        """Called when the DataProfiler finishes. Emits ProfilingCompleted."""
        self._transition(SessionStatus.PROFILED)
        self.profile = profile
        self._record_event(
            ProfilingCompleted(
                dataset_id=self.dataset_id,
                session_id=self.id,
                row_count=profile.row_count,
                column_count=profile.column_count,
                completeness_score=profile.completeness_score,
                correlation_id=self.correlation_id,
            )
        )

    def begin_cleaning(self) -> None:
        self._transition(SessionStatus.CLEANING)

    def complete_cleaning(self, report: CleaningReport) -> None:
        """Called when the DataCleaner finishes. Emits CleaningCompleted."""
        self._transition(SessionStatus.CLEANED)
        self.cleaning_report = report
        self._record_event(
            CleaningCompleted(
                dataset_id=self.dataset_id,
                session_id=self.id,
                rows_before=report.rows_before,
                rows_after=report.rows_after,
                correlation_id=self.correlation_id,
            )
        )

    def begin_analysis(self) -> None:
        self._transition(SessionStatus.ANALYSING)

    def complete_analysis(self, anomaly_ids: list[str] | None = None) -> None:
        """Called when all analysis agents finish."""
        self._transition(SessionStatus.COMPLETE)
        self.completed_at = datetime.now(UTC)
        if anomaly_ids:
            self.anomaly_ids = anomaly_ids
            self._record_event(
                AnomaliesDetected(
                    dataset_id=self.dataset_id,
                    session_id=self.id,
                    anomaly_count=len(anomaly_ids),
                    correlation_id=self.correlation_id,
                )
            )

    def mark_failed(self, reason: str) -> None:
        """Transition to FAILED from any non-terminal state."""
        self._transition(SessionStatus.FAILED)
        self.error_message = reason
        self.completed_at = datetime.now(UTC)

    # ── Derived helpers ───────────────────────────────────────────────────

    @property
    def is_terminal(self) -> bool:
        return self.status in (SessionStatus.COMPLETE, SessionStatus.FAILED)

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @classmethod
    def create(cls, session_id: str, dataset_id: str, correlation_id: str) -> AnalysisSession:
        """Factory — creates a new pending session."""
        return cls(
            id=session_id,
            dataset_id=dataset_id,
            correlation_id=correlation_id,
            started_at=datetime.now(UTC),
        )
