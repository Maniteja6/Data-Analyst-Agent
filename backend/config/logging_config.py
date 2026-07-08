"""Structured logging configuration via structlog.

Structlog is configured once at application startup (via ``configure_logging``)
and then used throughout the codebase as::

    import structlog
    logger = structlog.get_logger(__name__)
    logger.info("dataset_uploaded", dataset_id="abc-123", size_bytes=4096)

In development the output is colourised and human-readable.
In staging/production it is newline-delimited JSON, ready for ingestion
by CloudWatch Logs, Datadog, or any log aggregator.

The ``bind_contextvars`` helpers from structlog are used by the
``CorrelationIdMiddleware`` to attach ``correlation_id`` to every log
line emitted during a request, without passing it as a parameter.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(log_level: str = "INFO", *, json_logs: bool | None = None) -> None:
    """Initialise structlog for the application.

    Should be called once, at the very start of the lifespan handler
    in ``api/main.py``, before any logger is used.

    Args:
        log_level:  Root log level string — ``DEBUG | INFO | WARNING | ERROR``.
        json_logs:  Force JSON output (True) or pretty output (False).
                    Defaults to pretty in development and JSON otherwise.
                    Pass ``True`` explicitly when running inside a container.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # ── Shared processors applied to every log record ─────────────────────
    shared_processors: list = [
        # Merge any key-value pairs bound via structlog.contextvars
        # (e.g. correlation_id bound by CorrelationIdMiddleware)
        structlog.contextvars.merge_contextvars,
        # Add the log level as a string field: {"level": "info"}
        structlog.stdlib.add_log_level,
        # Add the logger name: {"logger": "backend.api.routers.datasets"}
        structlog.stdlib.add_logger_name,
        # Add ISO-8601 timestamp: {"timestamp": "2024-11-01T14:32:00.123456Z"}
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        # Render positional args in log calls: logger.info("msg %s", value)
        structlog.stdlib.PositionalArgumentsFormatter(),
        # Render stack_info if present
        structlog.processors.StackInfoRenderer(),
        # Format exc_info tracebacks into the event dict
        structlog.processors.format_exc_info,
    ]

    # ── Determine output format ────────────────────────────────────────────
    # Auto-detect: pretty in dev, JSON in staging/production.
    # Can be overridden by the caller.
    from backend.config.settings import get_settings

    settings = get_settings()
    use_json = json_logs if json_logs is not None else (settings.app_env != "development")

    if use_json:
        # Newline-delimited JSON — consumed by CloudWatch / Datadog
        renderer = structlog.processors.JSONRenderer()
    else:
        # Colourised key=value output — human-readable in local dev
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    # ── Configure structlog ────────────────────────────────────────────────
    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # ── Configure the stdlib logging root ────────────────────────────────
    # structlog wraps stdlib logging so that third-party libraries
    # (SQLAlchemy, aiokafka, boto3) also emit structured output.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    # Quieten noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.DEBUG if settings.debug else logging.WARNING
    )
    logging.getLogger("aiokafka").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Convenience wrapper — returns a named structlog logger.

    Prefer importing structlog directly in most modules::

        import structlog
        logger = structlog.get_logger(__name__)

    Use this helper when you want to avoid importing structlog in
    files that might be imported before ``configure_logging`` is called.
    """
    return structlog.get_logger(name)
