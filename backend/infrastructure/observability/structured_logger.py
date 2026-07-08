"""Structured logger — per-module logger factory and context helpers.

All application code should obtain loggers via this module rather than
importing structlog directly, so that:

1. There is a single place to change the logger factory if needed.
2. Contextual fields (``correlation_id``, ``dataset_id``, etc.) are always
   bound before the first log call rather than passed per-call.
3. Test code can swap the logger factory for a ``BoundLogger`` that captures
   log records for assertion.

Usage::

    from backend.infrastructure.observability.structured_logger import get_logger, bind_context

    logger = get_logger(__name__)

    # Bind request-scoped fields once (e.g. in FastAPI middleware)
    bind_context(correlation_id="abc-123", user_id="u-456")

    # Use the logger anywhere in the same async context
    logger.info("dataset_uploaded", dataset_id="ds-789", size_bytes=4096)
    logger.warning("slow_query", duration_ms=1200, sql="SELECT …")
    logger.error("bedrock_timeout", model="claude-sonnet-4-5", attempt=3)

Structured output format:

    Development (pretty, colourised):
        2024-11-01 14:32:00 [INFO     ] dataset_uploaded dataset_id=ds-789 size_bytes=4096

    Staging / Production (JSON, ingested by CloudWatch / Datadog):
        {
          "timestamp": "2024-11-01T14:32:00.123456Z",
          "level": "info",
          "logger": "backend.api.routers.datasets",
          "event": "dataset_uploaded",
          "correlation_id": "abc-123",
          "dataset_id": "ds-789",
          "size_bytes": 4096
        }
"""

from __future__ import annotations

from typing import Any

import structlog

# ---------------------------------------------------------------------------
# Logger factory
# ---------------------------------------------------------------------------


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog ``BoundLogger`` for the given module name.

    Args:
        name: Typically ``__name__`` of the calling module.
              Appears as the ``logger`` field in JSON output.

    Returns:
        A ``BoundLogger`` instance. Cheap to construct — structlog caches
        the processor chain after the first call when
        ``cache_logger_on_first_use=True`` is set in ``logging_config.py``.
    """
    return structlog.get_logger(name)


# ---------------------------------------------------------------------------
# Context binding helpers (structlog context variables)
# ---------------------------------------------------------------------------


def bind_context(**fields: Any) -> None:  # noqa: ANN401
    """Bind key-value pairs to the current async context.

    All subsequent log calls in the same async task / request will include
    these fields automatically via ``merge_contextvars``.

    Typically called once per request in ``CorrelationIdMiddleware``:

        bind_context(correlation_id="abc-123", endpoint="/api/v1/datasets")

    And once per Celery task in the ``task_prerun`` signal handler:

        bind_context(celery_task_id="...", celery_task_name="analysis.run_pipeline")

    Args:
        **fields: Arbitrary key-value pairs to add to the log context.
    """
    structlog.contextvars.bind_contextvars(**fields)


def unbind_context(*keys: str) -> None:
    """Remove specific keys from the current async context.

    Useful for removing sensitive fields (e.g. ``user_id``) before
    the log context spills into a different request's scope.
    """
    structlog.contextvars.unbind_contextvars(*keys)


def clear_context() -> None:
    """Clear all contextual fields from the current async context.

    Called at the end of each request (in middleware teardown) and at the
    end of each Celery task (in the ``task_postrun`` signal handler) to
    prevent context leakage between requests.
    """
    structlog.contextvars.clear_contextvars()


def get_context() -> dict[str, Any]:
    """Return a snapshot of all currently bound context variables.

    Useful for debugging middleware ordering issues or for embedding the
    context into a domain event (e.g. to propagate ``correlation_id``).
    """
    return structlog.contextvars.get_contextvars()


# ---------------------------------------------------------------------------
# Convenience log-level shortcuts
# ---------------------------------------------------------------------------


def log_info(logger_name: str, event: str, **fields: Any) -> None:  # noqa: ANN401
    """One-liner structured info log — useful in short utility functions."""
    get_logger(logger_name).info(event, **fields)


def log_warning(logger_name: str, event: str, **fields: Any) -> None:  # noqa: ANN401
    """One-liner structured warning log."""
    get_logger(logger_name).warning(event, **fields)


def log_error(logger_name: str, event: str, exc: Exception | None = None, **fields: Any) -> None:  # noqa: ANN401
    """One-liner structured error log with optional exception info."""
    if exc is not None:
        fields["error"] = str(exc)
        fields["error_type"] = type(exc).__name__
    get_logger(logger_name).error(event, **fields)


# ---------------------------------------------------------------------------
# Agent execution logger
# ---------------------------------------------------------------------------


class AgentLogger:
    """Structured logger pre-bound with agent name for use inside agent classes.

    Agents obtain an instance in ``BaseAgent.__init__`` and call it
    like a regular structlog logger. All events automatically include
    ``agent_name`` as a field.

    Usage inside a BaseAgent subclass::

        self._logger = AgentLogger(self.name)
        self._logger.info("agent_start", attempt=1, session_id="…")
        self._logger.warning("retry", error="ThrottlingException", delay=4.0)
    """

    def __init__(self, agent_name: str) -> None:
        self._log = structlog.get_logger(f"datapilot.agent.{agent_name}").bind(
            agent_name=agent_name
        )

    def info(self, event: str, **fields: Any) -> None:  # noqa: ANN401
        self._log.info(event, **fields)

    def warning(self, event: str, **fields: Any) -> None:  # noqa: ANN401
        self._log.warning(event, **fields)

    def error(self, event: str, **fields: Any) -> None:  # noqa: ANN401
        self._log.error(event, **fields)

    def debug(self, event: str, **fields: Any) -> None:  # noqa: ANN401
        self._log.debug(event, **fields)

    def bind(self, **fields: Any) -> AgentLogger:  # noqa: ANN401
        """Return a new AgentLogger with additional bound fields."""
        new = AgentLogger.__new__(AgentLogger)
        new._log = self._log.bind(**fields)
        return new
