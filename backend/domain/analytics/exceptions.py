"""Analytics domain exceptions."""
from __future__ import annotations

from backend.shared.exceptions import DomainException


class AnalyticsException(DomainException):
    """Base exception for the analytics bounded context."""


class SessionNotFoundException(AnalyticsException):
    def __init__(self, session_id: str) -> None:
        super().__init__(
            f"AnalysisSession '{session_id}' not found.",
            code="SESSION_NOT_FOUND",
        )
        self.session_id = session_id


class InvalidSessionStateError(AnalyticsException):
    """Raised when an operation is attempted on a session in the wrong state."""

    def __init__(self, session_id: str, current_state: str, required_state: str) -> None:
        super().__init__(
            f"Session '{session_id}' is in state '{current_state}' "
            f"but '{required_state}' is required.",
            code="INVALID_SESSION_STATE",
        )
        self.session_id     = session_id
        self.current_state  = current_state
        self.required_state = required_state


class ProfilingFailedError(AnalyticsException):
    """Raised when the data profiling step cannot complete."""

    def __init__(self, session_id: str, reason: str) -> None:
        super().__init__(
            f"Profiling failed for session '{session_id}': {reason}",
            code="PROFILING_FAILED",
        )
        self.session_id = session_id
        self.reason     = reason


class InsufficientDataError(AnalyticsException):
    """Raised when a dataset has too few rows or columns for meaningful analysis."""

    def __init__(self, row_count: int, min_rows: int = 10) -> None:
        super().__init__(
            f"Dataset has only {row_count} rows; at least {min_rows} are required.",
            code="INSUFFICIENT_DATA",
        )
        self.row_count = row_count
        self.min_rows  = min_rows
