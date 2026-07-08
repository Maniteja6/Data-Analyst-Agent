"""Prometheus metrics definitions for DataPilot.

All ``Counter``, ``Histogram``, ``Gauge``, and ``Summary`` objects are
defined here as module-level singletons. Application code imports and
uses them directly — no factory or registry injection needed.

The ``/metrics`` endpoint is exposed by ``prometheus_fastapi_instrumentator``
mounted in ``api/main.py`` when ``Settings.prometheus_enabled`` is True.

Metric naming conventions:
    ``datapilot_<subsystem>_<noun>_<unit>``

    Examples:
        datapilot_datasets_uploaded_total
        datapilot_agent_duration_seconds
        datapilot_llm_tokens_total

Label naming conventions:
    snake_case, short, enumerable (avoid high-cardinality labels like user_id)

Viewing metrics locally:
    curl http://localhost:8000/metrics

Grafana dashboard queries (PromQL examples):
    # Dataset processing throughput
    rate(datapilot_datasets_uploaded_total[5m])

    # Agent P95 latency by agent name
    histogram_quantile(0.95, sum(rate(datapilot_agent_duration_seconds_bucket[5m]))
        by (le, agent_name))

    # Bedrock cost rate (USD/minute)
    rate(datapilot_llm_cost_usd_total[1m]) * 60

    # Active WebSocket connections
    datapilot_websocket_connections_active
"""

from __future__ import annotations

from typing import Any

from prometheus_client import REGISTRY, Counter, Gauge, Histogram


# Guard against double-registration (e.g. during test collection)
def _metric(
    cls: type[Counter | Gauge | Histogram],
    name: str,
    documentation: str,
    **kwargs: Any,  # noqa: ANN401 — forwarded to a Prometheus metric constructor
) -> Counter | Gauge | Histogram:
    """Create a Prometheus metric, skipping if already registered."""
    try:
        return cls(name, documentation, **kwargs)
    except ValueError:
        # Metric already registered — return the existing collector
        return REGISTRY._names_to_collectors.get(name) or cls(name, documentation, **kwargs)


# ---------------------------------------------------------------------------
# Dataset lifecycle
# ---------------------------------------------------------------------------

datasets_uploaded_total = _metric(
    Counter,
    "datapilot_datasets_uploaded_total",
    "Total number of dataset files uploaded by users.",
    labelnames=["mime_type"],
)
"""Incremented in ``UploadDatasetUseCase.execute()`` after S3 upload succeeds."""

datasets_processing_total = _metric(
    Counter,
    "datapilot_datasets_processing_total",
    "Total dataset processing pipeline runs started.",
)

datasets_completed_total = _metric(
    Counter,
    "datapilot_datasets_completed_total",
    "Total datasets that completed the full pipeline successfully.",
)

datasets_failed_total = _metric(
    Counter,
    "datapilot_datasets_failed_total",
    "Total datasets that failed at any pipeline stage.",
    labelnames=["stage"],  # uploaded | profiling | cleaning | agents
)

dataset_size_bytes = _metric(
    Histogram,
    "datapilot_dataset_size_bytes",
    "Distribution of uploaded dataset file sizes in bytes.",
    buckets=[
        1_024,  # 1 KB
        10_240,  # 10 KB
        102_400,  # 100 KB
        1_048_576,  # 1 MB
        10_485_760,  # 10 MB
        104_857_600,  # 100 MB
        1_073_741_824,  # 1 GB
    ],
)

dataset_row_count = _metric(
    Histogram,
    "datapilot_dataset_row_count",
    "Distribution of row counts after profiling.",
    buckets=[100, 1_000, 10_000, 100_000, 500_000, 1_000_000, 5_000_000],
)

pipeline_duration_seconds = _metric(
    Histogram,
    "datapilot_pipeline_duration_seconds",
    "End-to-end analytics pipeline duration in seconds.",
    labelnames=["stage"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600],
)

# ---------------------------------------------------------------------------
# Agent performance
# ---------------------------------------------------------------------------

agent_executions_total = _metric(
    Counter,
    "datapilot_agent_executions_total",
    "Total agent invocations by agent name and outcome.",
    labelnames=["agent_name", "status"],  # status: success | failure | retry
)
"""Incremented by ``BaseAgent.run()`` after each invocation completes."""

agent_duration_seconds = _metric(
    Histogram,
    "datapilot_agent_duration_seconds",
    "Agent wall-clock execution time in seconds.",
    labelnames=["agent_name"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)

agent_retry_total = _metric(
    Counter,
    "datapilot_agent_retry_total",
    "Total agent retry attempts.",
    labelnames=["agent_name"],
)

# ---------------------------------------------------------------------------
# LLM / Bedrock
# ---------------------------------------------------------------------------

llm_tokens_total = _metric(
    Counter,
    "datapilot_llm_tokens_total",
    "Total LLM tokens consumed split by agent and token type.",
    labelnames=["agent_name", "model", "token_type"],  # token_type: input | output
)
"""Incremented by ``TokenTracker.record()`` after each Bedrock call."""

llm_cost_usd_total = _metric(
    Counter,
    "datapilot_llm_cost_usd_total",
    "Estimated cumulative Bedrock cost in USD.",
    labelnames=["agent_name", "model"],
)

llm_latency_seconds = _metric(
    Histogram,
    "datapilot_llm_latency_seconds",
    "Bedrock Converse / InvokeModel round-trip latency in seconds.",
    labelnames=["model"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0],
)

llm_cache_hits_total = _metric(
    Counter,
    "datapilot_llm_cache_hits_total",
    "Total LLM response cache hits (Bedrock API call avoided).",
    labelnames=["agent_name"],
)

llm_errors_total = _metric(
    Counter,
    "datapilot_llm_errors_total",
    "Total Bedrock API errors by error code.",
    labelnames=["error_code"],  # ThrottlingException | ModelNotReadyException | etc.
)

# ---------------------------------------------------------------------------
# Chat / WebSocket
# ---------------------------------------------------------------------------

chat_messages_total = _metric(
    Counter,
    "datapilot_chat_messages_total",
    "Total chat messages by role.",
    labelnames=["role"],  # user | assistant
)

chat_session_duration_seconds = _metric(
    Histogram,
    "datapilot_chat_session_duration_seconds",
    "Chat session duration from first to last message in seconds.",
    buckets=[30, 60, 120, 300, 600, 1800, 3600],
)

websocket_connections_active = _metric(
    Gauge,
    "datapilot_websocket_connections_active",
    "Number of currently active WebSocket (Socket.IO) connections.",
)

websocket_events_total = _metric(
    Counter,
    "datapilot_websocket_events_total",
    "Total WebSocket events emitted by event type.",
    labelnames=["event_type"],
)

# ---------------------------------------------------------------------------
# Celery job queue
# ---------------------------------------------------------------------------

celery_queue_depth = _metric(
    Gauge,
    "datapilot_celery_queue_depth",
    "Number of tasks waiting in each Celery queue.",
    labelnames=["queue"],
)
"""Updated by a periodic beat task that inspects the broker queue lengths."""

celery_task_duration_seconds = _metric(
    Histogram,
    "datapilot_celery_task_duration_seconds",
    "Celery task execution time in seconds.",
    labelnames=["task_name", "status"],
    buckets=[1, 5, 15, 30, 60, 120, 300, 600],
)

# ---------------------------------------------------------------------------
# Data quality
# ---------------------------------------------------------------------------

anomalies_detected_total = _metric(
    Counter,
    "datapilot_anomalies_detected_total",
    "Total anomalies detected by severity and detection method.",
    labelnames=["severity", "method"],
)

data_quality_score = _metric(
    Histogram,
    "datapilot_data_quality_score",
    "Distribution of composite data quality scores (0.0–1.0).",
    buckets=[0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0],
)

# ---------------------------------------------------------------------------
# Infrastructure health
# ---------------------------------------------------------------------------

db_query_duration_seconds = _metric(
    Histogram,
    "datapilot_db_query_duration_seconds",
    "PostgreSQL query duration in seconds.",
    labelnames=["operation"],  # select | insert | update | delete
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)

s3_operation_duration_seconds = _metric(
    Histogram,
    "datapilot_s3_operation_duration_seconds",
    "S3/MinIO operation duration in seconds.",
    labelnames=["operation"],  # upload | download | delete | presign
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 15.0, 30.0],
)

kafka_events_published_total = _metric(
    Counter,
    "datapilot_kafka_events_published_total",
    "Total domain events published to Kafka by event type.",
    labelnames=["event_type", "topic"],
)

kafka_events_consumed_total = _metric(
    Counter,
    "datapilot_kafka_events_consumed_total",
    "Total Kafka events consumed by consumer group.",
    labelnames=["topic", "consumer_group"],
)

# ---------------------------------------------------------------------------
# Convenience emission helpers
# ---------------------------------------------------------------------------


def record_agent_execution(
    agent_name: str,
    status: str,
    duration_seconds: float,
    model: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float = 0.0,
) -> None:
    """Emit all agent-related metrics for one invocation in a single call.

    Called by ``BaseAgent.run()`` after each execution:

        record_agent_execution(
            agent_name="sql",
            status="success",
            duration_seconds=1.23,
            model="anthropic.claude-sonnet-4-5",
            input_tokens=512,
            output_tokens=128,
            cost_usd=0.0042,
        )
    """
    agent_executions_total.labels(agent_name=agent_name, status=status).inc()
    agent_duration_seconds.labels(agent_name=agent_name).observe(duration_seconds)

    if model:
        llm_tokens_total.labels(agent_name=agent_name, model=model, token_type="input").inc(
            input_tokens
        )
        llm_tokens_total.labels(agent_name=agent_name, model=model, token_type="output").inc(
            output_tokens
        )
        llm_cost_usd_total.labels(agent_name=agent_name, model=model).inc(cost_usd)


def record_bedrock_call(
    model: str,
    latency_ms: int,
    input_tokens: int,
    output_tokens: int,
    error_code: str | None = None,
) -> None:
    """Emit Bedrock-specific metrics after each Converse / InvokeModel call.

    Called by ``BedrockConverseAdapter`` and ``BedrockStreamAdapter``.
    """
    llm_latency_seconds.labels(model=model).observe(latency_ms / 1000)
    if error_code:
        llm_errors_total.labels(error_code=error_code).inc()


def record_dataset_upload(mime_type: str, size_bytes: int) -> None:
    """Emit upload metrics immediately after a file is stored in S3."""
    datasets_uploaded_total.labels(mime_type=mime_type).inc()
    dataset_size_bytes.observe(size_bytes)


def record_anomaly(severity: str, method: str) -> None:
    """Increment the anomaly counter for one detected anomaly."""
    anomalies_detected_total.labels(severity=severity, method=method).inc()
