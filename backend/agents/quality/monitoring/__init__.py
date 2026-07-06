"""Agent sub-package."""
"""Monitoring agent — Prometheus metrics, OTel spans, and audit logging.

MetricsEmitter:      emits 11 Prometheus metrics after each agent run.
TraceInstrumentor:   agent_span(), pipeline_span(), websocket_span() context managers.
MonitoringAgent:     called by OrchestratorAgent post-DAG; non-blocking Postgres write.
Emits: monitoring:agent_slow (>10s), monitoring:cost_alert (>$0.10),
       monitoring:pipeline_report (to monitoring:<dataset_id> admin room).
"""
from backend.agents.quality.monitoring.monitoring_agent   import MonitoringAgent
from backend.agents.quality.monitoring.metrics_emitter    import MetricsEmitter
from backend.agents.quality.monitoring.trace_instrumentor import (
    agent_span, pipeline_span, websocket_span,
)

__all__ = [
    "MonitoringAgent", "MetricsEmitter",
    "agent_span", "pipeline_span", "websocket_span",
]
