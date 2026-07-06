"""Observability — structured logging, OpenTelemetry tracing, Prometheus metrics, audit logging."""
"""Observability — structured logging, OTel traces, Prometheus metrics, audit log.

configure_logging():  structlog JSON; binds correlation_id as context var.
setup_otel():         OTLP exporter to Grafana Tempo / Jaeger.
All 11 Prometheus metrics defined in prometheus_metrics.py; imported by MetricsEmitter.
AuditLogger:          append-only writes to agent_executions Postgres table.
"""
from backend.infrastructure.observability.structured_logger import configure_logging
from backend.infrastructure.observability.otel_setup        import setup_otel

__all__ = ["configure_logging", "setup_otel"]
