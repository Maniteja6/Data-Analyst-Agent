"""MetricsEmitter — emits Prometheus counters and histograms for each agent run.

Real-time design:
    MetricsEmitter is called by MonitoringAgent after every pipeline task
    completes. Prometheus metrics are used for:
    - Agent latency (histogram per agent, P50/P95/P99)
    - Token consumption (counter per model_id)
    - Pipeline success/failure rates (counter per stage)
    - WebSocket connection count (gauge)
    - Bedrock API cost (counter per model)

    All metrics are exposed on ``/metrics`` via ``prometheus_fastapi_instrumentator``
    and scraped by Prometheus at 15-second intervals. Grafana dashboards
    alert on P95 latency > 10s and error rate > 5%.

    ``emit_pipeline_metrics()`` is the primary method called by MonitoringAgent.
    ``emit_ws_event()`` is called by the WebSocket handlers for connection tracking.
"""
from __future__ import annotations

import structlog

from backend.agents.base.agent_result import AgentResult

logger = structlog.get_logger(__name__)


class MetricsEmitter:
    """Emits Prometheus metrics for completed pipeline tasks.

    Args:
        namespace: Prometheus metric namespace prefix (default: ``datapilot``).
    """

    def __init__(self, namespace: str = "datapilot") -> None:
        self._ns   = namespace
        self._prom = self._load_prometheus()

    def emit_agent_metrics(self, result: AgentResult) -> None:
        """Emit timing, token, and cost metrics for one completed agent task.

        Args:
            result: AgentResult from BaseAgent.run().
        """
        if not self._prom:
            return
        try:
            m = self._prom

            # Agent latency histogram
            m["agent_duration_ms"].labels(
                agent=result.agent_name,
                status="success" if result.success else "failure",
            ).observe(result.duration_ms)

            # Success / failure counter
            m["agent_runs_total"].labels(
                agent=result.agent_name,
                status="success" if result.success else "failure",
            ).inc()

            # Token consumption
            if result.token_input or result.token_output:
                m["llm_tokens_total"].labels(
                    agent=result.agent_name,
                    model=result.model_id or "unknown",
                    token_type="input",
                ).inc(result.token_input)
                m["llm_tokens_total"].labels(
                    agent=result.agent_name,
                    model=result.model_id or "unknown",
                    token_type="output",
                ).inc(result.token_output)

            # Cost counter
            if result.estimated_cost_usd > 0:
                m["llm_cost_usd_total"].labels(
                    agent=result.agent_name,
                    model=result.model_id or "unknown",
                ).inc(result.estimated_cost_usd)

        except Exception as exc:
            logger.debug("metrics_emit_failed", error=str(exc))

    def emit_pipeline_metrics(
        self,
        dataset_id: str,
        succeeded:  int,
        failed:     int,
        total_ms:   int,
        cost_usd:   float,
    ) -> None:
        """Emit end-of-pipeline aggregate metrics."""
        if not self._prom:
            return
        try:
            m = self._prom
            m["pipeline_duration_ms"].observe(total_ms)
            m["pipeline_runs_total"].labels(
                status="success" if failed == 0 else "partial" if succeeded > 0 else "failure"
            ).inc()
            m["pipeline_cost_usd_total"].inc(cost_usd)
        except Exception as exc:
            logger.debug("pipeline_metrics_emit_failed", error=str(exc))

    def emit_ws_event(self, event: str, dataset_id: str = "") -> None:
        """Track WebSocket message events."""
        if not self._prom:
            return
        try:
            self._prom["ws_messages_total"].labels(event=event).inc()
        except Exception:
            pass

    def emit_rag_metrics(self, query_ms: int, chunks_retrieved: int, top_score: float) -> None:
        """Track RAG retrieval performance."""
        if not self._prom:
            return
        try:
            m = self._prom
            m["rag_retrieval_ms"].observe(query_ms)
            m["rag_chunks_retrieved"].observe(chunks_retrieved)
            m["rag_top_score"].observe(top_score)
        except Exception:
            pass

    # ── Prometheus setup ──────────────────────────────────────────────────

    def _load_prometheus(self) -> dict | None:
        """Return a dict of Prometheus metric objects, or None if unavailable."""
        try:
            from prometheus_client import Counter, Histogram, Gauge

            ns = self._ns
            return {
                "agent_duration_ms": Histogram(
                    f"{ns}_agent_duration_ms",
                    "Agent execution time in milliseconds",
                    ["agent", "status"],
                    buckets=[100, 500, 1000, 2500, 5000, 10000, 30000],
                ),
                "agent_runs_total": Counter(
                    f"{ns}_agent_runs_total",
                    "Total agent executions by status",
                    ["agent", "status"],
                ),
                "llm_tokens_total": Counter(
                    f"{ns}_llm_tokens_total",
                    "Total LLM tokens consumed",
                    ["agent", "model", "token_type"],
                ),
                "llm_cost_usd_total": Counter(
                    f"{ns}_llm_cost_usd_total",
                    "Total estimated Bedrock API cost in USD",
                    ["agent", "model"],
                ),
                "pipeline_duration_ms": Histogram(
                    f"{ns}_pipeline_duration_ms",
                    "Full pipeline execution time",
                    buckets=[5000, 10000, 30000, 60000, 120000],
                ),
                "pipeline_runs_total": Counter(
                    f"{ns}_pipeline_runs_total",
                    "Total pipeline runs by status",
                    ["status"],
                ),
                "pipeline_cost_usd_total": Counter(
                    f"{ns}_pipeline_cost_usd_total",
                    "Total estimated pipeline cost in USD",
                ),
                "ws_messages_total": Counter(
                    f"{ns}_ws_messages_total",
                    "Total WebSocket messages by event type",
                    ["event"],
                ),
                "rag_retrieval_ms": Histogram(
                    f"{ns}_rag_retrieval_ms",
                    "RAG retrieval latency in milliseconds",
                    buckets=[10, 50, 100, 250, 500, 1000],
                ),
                "rag_chunks_retrieved": Histogram(
                    f"{ns}_rag_chunks_retrieved",
                    "Number of chunks returned per RAG query",
                    buckets=[1, 2, 4, 8, 16],
                ),
                "rag_top_score": Histogram(
                    f"{ns}_rag_top_score",
                    "Top cosine similarity score per RAG query",
                    buckets=[0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
                ),
            }
        except ImportError:
            logger.debug("prometheus_client_not_installed")
            return None
        except ValueError:
            # Metric already registered (happens in tests with multiple test runs)
            return None
