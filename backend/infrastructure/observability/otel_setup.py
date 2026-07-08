"""OpenTelemetry SDK initialisation for DataPilot.

Sets up distributed tracing so every inbound request, Celery task, Kafka
consumer, Bedrock API call, and database query appears as a linked span in
Jaeger / Grafana Tempo / AWS X-Ray.

Architecture:
- Traces are exported via OTLP gRPC to a collector sidecar (or the
  OpenTelemetry Collector running as a DaemonSet in EKS).
- The collector routes spans to Jaeger (dev), Grafana Tempo (staging), or
  AWS X-Ray (production) via a pipeline defined in collector config.
- Each service (api, worker, celery-beat) has its own ``otel_service_name``
  so Jaeger shows them as separate services in the trace topology.

Usage (called once in the FastAPI lifespan handler):

    from backend.infrastructure.observability.otel_setup import (
        setup_otel, instrument_fastapi, get_tracer
    )

    setup_otel(service_name="datapilot-api", endpoint="http://localhost:4317")
    instrument_fastapi(app)

    # Inside application code:
    tracer = get_tracer("backend.agents.sql")
    with tracer.start_as_current_span("sql_agent.execute") as span:
        span.set_attribute("sql.query", sql)
        span.set_attribute("sql.row_limit", row_limit)
        result = await duckdb_executor.execute(sql)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    import redis.asyncio as redis
    from fastapi import FastAPI
    from sqlalchemy import Engine
    from sqlalchemy.ext.asyncio import AsyncEngine

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Core setup
# ---------------------------------------------------------------------------


def setup_otel(
    service_name: str,
    endpoint: str,
    *,
    protocol: str = "grpc",
    additional_resource_attributes: dict[str, str] | None = None,
) -> None:
    """Initialise the OpenTelemetry SDK and configure the OTLP exporter.

    This function is idempotent — calling it multiple times in the same
    process (e.g. in tests) is safe; subsequent calls are no-ops.

    Args:
        service_name:                   Service name tag for all spans.
        endpoint:                       OTLP gRPC endpoint, e.g. ``'http://localhost:4317'``.
        protocol:                       ``'grpc'`` (default) or ``'http/protobuf'``.
        additional_resource_attributes: Extra ``service.*`` attributes added to
                                        every span, e.g. ``{'service.version': '1.0.0'}``.
    """
    try:
        from backend.config.settings import get_settings
        from opentelemetry import trace
        from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        settings = get_settings()

        # Guard against double-initialisation
        current_provider = trace.get_tracer_provider()
        if not isinstance(current_provider, trace.ProxyTracerProvider):
            logger.debug("otel_already_configured", service_name=service_name)
            return

        # Build the resource describing this service
        resource_attrs = {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: settings.app_version,
            "deployment.environment": settings.app_env,
        }
        if additional_resource_attributes:
            resource_attrs.update(additional_resource_attributes)
        resource = Resource.create(resource_attrs)

        # Create the tracer provider
        provider = TracerProvider(resource=resource)

        # Configure the OTLP exporter
        if protocol == "grpc":
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(
                endpoint=endpoint,
                insecure=not endpoint.startswith("https"),
            )
        else:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")

        # Batch processor — buffers spans and sends in batches to reduce overhead
        provider.add_span_processor(
            BatchSpanProcessor(
                exporter,
                max_queue_size=2048,
                max_export_batch_size=512,
                export_timeout_millis=5000,
            )
        )

        trace.set_tracer_provider(provider)

        logger.info(
            "otel_configured",
            service_name=service_name,
            endpoint=endpoint,
            protocol=protocol,
        )

    except ImportError:
        logger.warning(
            "otel_import_failed",
            detail="opentelemetry-sdk not installed; tracing disabled",
        )
    except Exception as exc:
        # OTel setup failure must never crash the application
        logger.error("otel_setup_failed", error=str(exc))


# ---------------------------------------------------------------------------
# Instrumentation helpers
# ---------------------------------------------------------------------------


def instrument_fastapi(app: FastAPI) -> None:
    """Instrument a FastAPI application with automatic span creation.

    Creates one span per HTTP request with ``http.method``, ``http.url``,
    ``http.status_code``, and ``http.route`` attributes.

    Args:
        app: A ``FastAPI`` instance.
    """
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls="/health,/ready,/metrics",  # skip infra endpoints
        )
        logger.info("otel_fastapi_instrumented")
    except ImportError:
        logger.warning("otel_fastapi_instrumentation_unavailable")
    except Exception as exc:
        logger.error("otel_fastapi_instrument_failed", error=str(exc))


def instrument_sqlalchemy(engine: AsyncEngine | Engine) -> None:
    """Instrument a SQLAlchemy engine to trace all DB queries.

    Creates child spans under the active request span with
    ``db.statement``, ``db.system`` (postgresql), and ``db.operation``.

    Args:
        engine: A SQLAlchemy ``AsyncEngine`` or ``Engine`` instance.
    """
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument(engine=engine)
        logger.info("otel_sqlalchemy_instrumented")
    except ImportError:
        logger.warning("otel_sqlalchemy_instrumentation_unavailable")
    except Exception as exc:
        logger.error("otel_sqlalchemy_instrument_failed", error=str(exc))


def instrument_redis(client: redis.Redis) -> None:
    """Instrument a Redis client to trace cache operations.

    Args:
        client: A ``redis.asyncio.Redis`` instance.
    """
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
        logger.info("otel_redis_instrumented")
    except ImportError:
        logger.warning("otel_redis_instrumentation_unavailable")
    except Exception as exc:
        logger.error("otel_redis_instrument_failed", error=str(exc))


# ---------------------------------------------------------------------------
# Tracer factory
# ---------------------------------------------------------------------------


def get_tracer(name: str) -> Any:  # noqa: ANN401 — real OTel Tracer or no-op fallback
    """Return an OpenTelemetry ``Tracer`` for the given component name.

    When OTel is not configured (e.g. in unit tests), returns a no-op tracer
    that produces ``NonRecordingSpan`` objects which have zero overhead.

    Args:
        name: Typically the module ``__name__`` or a component label
              such as ``'datapilot.agent.sql'``.

    Usage::

        tracer = get_tracer(__name__)

        async def execute_query(sql: str) -> dict:
            with tracer.start_as_current_span("duckdb.execute") as span:
                span.set_attribute("sql.query", sql[:500])
                result = run_duckdb(sql)
                span.set_attribute("db.row_count", result["row_count"])
                return result
    """
    from opentelemetry import trace

    return trace.get_tracer(name)


# ---------------------------------------------------------------------------
# Span attribute helpers
# ---------------------------------------------------------------------------


def set_agent_attributes(span: Any, agent_name: str, session_id: str, attempt: int = 1) -> None:  # noqa: ANN401
    """Set standard agent span attributes in a single call.

    Standardises the attribute names used across all agents so Jaeger
    can filter and group spans by agent name, session, or attempt count.
    """
    try:
        span.set_attribute("agent.name", agent_name)
        span.set_attribute("agent.session_id", session_id)
        span.set_attribute("agent.attempt", attempt)
    except Exception as exc:
        logger.debug("agent_span_attributes_failed", error=str(exc))


def set_bedrock_attributes(
    span: Any,  # noqa: ANN401
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
) -> None:
    """Set Bedrock LLM span attributes."""
    try:
        span.set_attribute("llm.model_id", model_id)
        span.set_attribute("llm.input_tokens", input_tokens)
        span.set_attribute("llm.output_tokens", output_tokens)
        span.set_attribute("llm.latency_ms", latency_ms)
        span.set_attribute("llm.total_tokens", input_tokens + output_tokens)
    except Exception as exc:
        logger.debug("bedrock_span_attributes_failed", error=str(exc))


def record_exception(span: Any, exc: Exception) -> None:  # noqa: ANN401
    """Record an exception on the current span without propagating it.

    Sets the span status to ERROR and attaches the exception event
    so it appears in the Jaeger trace with full stack information.
    """
    try:
        from opentelemetry.trace import StatusCode

        span.record_exception(exc)
        span.set_status(StatusCode.ERROR, str(exc))
    except Exception as span_exc:
        logger.debug("span_exception_record_failed", error=str(span_exc))
