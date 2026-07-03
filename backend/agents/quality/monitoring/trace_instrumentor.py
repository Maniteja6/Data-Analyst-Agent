"""TraceInstrumentor — OpenTelemetry span management for the agent pipeline.

Real-time design:
    Every agent run creates a child span under the top-level pipeline span.
    For WebSocket chat queries, the trace propagates from the initial HTTP
    upgrade handshake through the Socket.IO message handler and all the way
    through InsightAgent and SecurityAgent.

    Trace IDs are included in every structured log event and in the
    ``X-Correlation-ID`` Socket.IO response headers so traces can be
    correlated with logs in Grafana or AWS X-Ray.

    ``agent_span()`` is the primary context manager used by BaseAgent.
    ``pipeline_span()`` wraps the full DAG execution from OrchestratorAgent.
    ``websocket_span()`` wraps individual WebSocket message handling.
"""
from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _get_tracer():
    """Return an OpenTelemetry tracer or a NoOp tracer when OTel is absent."""
    try:
        from opentelemetry import trace
        return trace.get_tracer("datapilot.agents")
    except ImportError:
        return _NoOpTracer()


@contextmanager
def agent_span(
    agent_name:     str,
    session_id:     str = "",
    dataset_id:     str = "",
    correlation_id: str = "",
):
    """Synchronous context manager that wraps one agent execution in an OTel span.

    Used by BaseAgent._otel_span() as the instrumentation hook.

    Usage::

        with agent_span("sql", session_id=ctx.session_id):
            result = await sql_agent._execute(context, question="...")
    """
    tracer = _get_tracer()
    with tracer.start_as_current_span(
        f"agent.{agent_name}",
        attributes={
            "agent.name":       agent_name,
            "session.id":       session_id,
            "dataset.id":       dataset_id,
            "correlation.id":   correlation_id,
        },
    ) as span:
        try:
            yield span
        except Exception as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(exc))
            raise


@asynccontextmanager
async def pipeline_span(
    session_id: str,
    dataset_id: str,
    plan_id:    str = "",
):
    """Async context manager wrapping the full DAG execution pipeline."""
    tracer = _get_tracer()
    with tracer.start_as_current_span(
        "pipeline.execute",
        attributes={
            "session.id": session_id,
            "dataset.id": dataset_id,
            "plan.id":    plan_id,
        },
    ) as span:
        try:
            yield span
        except Exception as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(exc))
            raise


@asynccontextmanager
async def websocket_span(
    event_type:      str,
    conversation_id: str = "",
    dataset_id:      str = "",
    correlation_id:  str = "",
):
    """Async context manager wrapping one WebSocket message handler."""
    tracer = _get_tracer()
    with tracer.start_as_current_span(
        f"ws.{event_type}",
        attributes={
            "ws.event":          event_type,
            "conversation.id":   conversation_id,
            "dataset.id":        dataset_id,
            "correlation.id":    correlation_id,
        },
    ) as span:
        try:
            yield span
        except Exception as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(exc))
            raise


def set_span_attribute(key: str, value: Any) -> None:
    """Set an attribute on the currently active OTel span.

    No-ops when no span is active or OTel is not installed.
    """
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute(key, str(value))
    except Exception:
        pass


def add_span_event(name: str, attributes: dict[str, Any] | None = None) -> None:
    """Add an event (structured log entry) to the current OTel span."""
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        if span and span.is_recording():
            span.add_event(name, attributes=attributes or {})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# No-Op tracer for environments without OpenTelemetry
# ---------------------------------------------------------------------------

class _NoOpSpan:
    """Span-like object that accepts all attribute/event calls without error."""
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def set_attribute(self, *_): pass
    def add_event(self, *_): pass
    def is_recording(self): return False


class _NoOpTracer:
    """Tracer that always returns _NoOpSpan objects."""
    def start_as_current_span(self, name, attributes=None, **_):
        return _NoOpSpan()
