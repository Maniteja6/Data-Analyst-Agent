"""Shared exception hierarchy for the DataPilot backend.

All custom exceptions inherit from ``DataPilotException``, making it
easy to catch all application-level errors at the API boundary with a
single ``except DataPilotException`` clause while still distinguishing
error types in more specific handlers.

Layer mapping:
    DomainException       — invariant violations inside the domain model
    ApplicationException  — use case / orchestration failures
    InfrastructureException — adapter / IO failures (DB, S3, Kafka, Bedrock)
    AgentException        — AI agent execution failures
    NotFoundException     — entity not found (maps to HTTP 404)
    ValidationException   — input validation failure (maps to HTTP 422)
    AuthorisationException — access denied (maps to HTTP 403)
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class DataPilotException(Exception):
    """Root exception for all application-level errors.

    Args:
        message: Human-readable description of the error.
        code:    Machine-readable error code (defaults to class name).
                 Used in API error responses and log correlation.
    """

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


# ---------------------------------------------------------------------------
# Domain layer
# ---------------------------------------------------------------------------

class DomainException(DataPilotException):
    """Raised when a domain invariant is violated.

    Examples:
        - Attempting an invalid status transition on a Dataset aggregate
        - A value object receiving an out-of-range value
    """


class InvalidStatusTransitionError(DomainException):
    """Raised when an aggregate is transitioned to a state that is not
    reachable from its current state.
    """

    def __init__(self, current: object, target: object) -> None:
        super().__init__(
            f"Cannot transition from '{current}' to '{target}'.",
            code="INVALID_STATUS_TRANSITION",
        )
        self.current = current
        self.target = target


# ---------------------------------------------------------------------------
# Application layer
# ---------------------------------------------------------------------------

class ApplicationException(DataPilotException):
    """Raised by use cases when orchestration logic fails."""


class ConflictException(ApplicationException):
    """Raised when an operation conflicts with existing state
    (e.g. duplicate dataset upload).
    """

    def __init__(self, resource: str, detail: str = "") -> None:
        msg = f"Conflict on '{resource}'" + (f": {detail}" if detail else ".")
        super().__init__(msg, code="CONFLICT")
        self.resource = resource


# ---------------------------------------------------------------------------
# Infrastructure layer
# ---------------------------------------------------------------------------

class InfrastructureException(DataPilotException):
    """Raised when an infrastructure adapter fails (DB, S3, Kafka, Bedrock)."""


class StorageException(InfrastructureException):
    """S3 / local storage operation failed."""


class CacheException(InfrastructureException):
    """Redis cache operation failed."""


class MessagingException(InfrastructureException):
    """Kafka publish / consume operation failed."""


class BedrockException(InfrastructureException):
    """AWS Bedrock API call failed after all retries exhausted."""


# ---------------------------------------------------------------------------
# Agent layer
# ---------------------------------------------------------------------------

class AgentException(DataPilotException):
    """Raised when an AI agent fails to complete its task.

    Args:
        agent_name: Name of the failing agent (e.g. 'planner', 'sql').
        reason:     Description of the failure.
    """

    def __init__(self, agent_name: str, reason: str) -> None:
        super().__init__(
            f"Agent '{agent_name}' failed: {reason}",
            code="AGENT_FAILURE",
        )
        self.agent_name = agent_name
        self.reason = reason


class AgentTimeoutError(AgentException):
    """Raised when an agent exceeds its configured execution timeout."""

    def __init__(self, agent_name: str, timeout_seconds: int) -> None:
        super().__init__(agent_name, f"Timed out after {timeout_seconds}s")
        self.timeout_seconds = timeout_seconds


class SQLInjectionDetectedError(AgentException):
    """Raised by the SQL validator when generated SQL contains blocked keywords."""

    def __init__(self, keyword: str) -> None:
        super().__init__("sql", f"Blocked SQL keyword detected: '{keyword}'")
        self.keyword = keyword


# ---------------------------------------------------------------------------
# Cross-cutting concerns
# ---------------------------------------------------------------------------

class NotFoundException(DataPilotException):
    """Raised when a requested entity does not exist.

    Maps to HTTP 404 in the API error handler.
    """

    def __init__(self, entity_type: str, entity_id: str) -> None:
        super().__init__(
            f"{entity_type} with id '{entity_id}' not found.",
            code="NOT_FOUND",
        )
        self.entity_type = entity_type
        self.entity_id = entity_id


class ValidationException(DataPilotException):
    """Raised when user-supplied input fails domain validation.

    Maps to HTTP 422 in the API error handler.
    """

    def __init__(self, field: str, reason: str) -> None:
        super().__init__(
            f"Validation failed for '{field}': {reason}",
            code="VALIDATION_ERROR",
        )
        self.field = field
        self.reason = reason


class UnsupportedFileTypeError(ValidationException):
    """Raised when an uploaded file has an unsupported extension."""

    def __init__(self, filename: str) -> None:
        super().__init__("filename", f"'{filename}' has an unsupported file type.")
        self.filename = filename


class FileTooLargeError(ValidationException):
    """Raised when an uploaded file exceeds the configured size limit."""

    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        size_mb = size_bytes / (1024 * 1024)
        max_mb  = max_bytes  / (1024 * 1024)
        super().__init__(
            "file",
            f"File size {size_mb:.1f} MB exceeds the {max_mb:.0f} MB limit.",
        )
        self.size_bytes = size_bytes
        self.max_bytes  = max_bytes


class AuthorisationException(DataPilotException):
    """Raised when a user attempts an action they are not authorised to perform.

    Maps to HTTP 403 in the API error handler.
    """

    def __init__(self, action: str, resource: str) -> None:
        super().__init__(
            f"Not authorised to perform '{action}' on '{resource}'.",
            code="FORBIDDEN",
        )
        self.action   = action
        self.resource = resource


class PIIDetectedError(DataPilotException):
    """Raised by the security agent when PII is found in user input or agent output."""

    def __init__(self, entity_types: list[str]) -> None:
        super().__init__(
            f"PII detected: {', '.join(entity_types)}. Request blocked.",
            code="PII_DETECTED",
        )
        self.entity_types = entity_types


class InjectionDetectedError(DataPilotException):
    """Raised when a prompt injection attempt is detected in user input."""

    def __init__(self, score: float) -> None:
        super().__init__(
            f"Prompt injection attempt detected (score={score:.2f}). Request blocked.",
            code="INJECTION_DETECTED",
        )
        self.score = score
