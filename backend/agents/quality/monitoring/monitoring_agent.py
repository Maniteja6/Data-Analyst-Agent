"""MonitoringAgent — emits metrics and traces after every pipeline run.

Real-time design:
    The MonitoringAgent is the final cross-cutting agent called by
    OrchestratorAgent after the DAG completes. It:

    1. Emits per-agent Prometheus metrics (latency, tokens, cost)
    2. Emits end-of-pipeline aggregate metrics
    3. Persists the agent execution audit log to Postgres
    4. Emits a ``monitoring:pipeline_report`` Socket.IO event with the
       full cost and performance breakdown — used by the admin dashboard

    The monitoring agent is NON-BLOCKING for the user. All Prometheus
    and Postgres writes happen asynchronously and never delay the
    ``analysis.complete`` Socket.IO event delivered to the user.

Socket.IO events emitted (to the admin monitoring room):
    monitoring:pipeline_report — full performance + cost breakdown
    monitoring:agent_slow      — when any agent exceeds the slow threshold
    monitoring:cost_alert      — when session cost exceeds the threshold
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from datetime import UTC
from typing import Any

import structlog
from backend.agents.base.agent_context import AgentContext
from backend.agents.base.agent_result import AgentResult
from backend.agents.base.base_agent import BaseAgent
from backend.agents.quality.monitoring.metrics_emitter import MetricsEmitter
from backend.agents.quality.monitoring.trace_instrumentor import add_span_event

logger = structlog.get_logger(__name__)

SLOW_AGENT_THRESHOLD_MS = 10_000  # 10 seconds
COST_ALERT_THRESHOLD = 0.10  # $0.10 per session


class MonitoringAgent(BaseAgent):
    """Emits metrics, traces, and audit logs for the completed pipeline.

    Args:
        metrics_emitter: MetricsEmitter instance (or None for auto-init).
    """

    def __init__(self, metrics_emitter: MetricsEmitter | None = None) -> None:
        super().__init__("monitoring")
        self._emitter = metrics_emitter or MetricsEmitter()

    async def _execute(
        self,
        context: AgentContext,
        task_results: dict[str, AgentResult] | None = None,
        start_time: float | None = None,
        **kwargs: Any,  # noqa: ANN401
    ) -> dict:
        """Emit all metrics and traces for the completed pipeline.

        Args:
            context:      Shared pipeline state.
            task_results: Dict of task_id → AgentResult from DAGExecutor.
            start_time:   Pipeline start time as ``time.monotonic()`` float.

        Returns:
            Dict with: agent_metrics, pipeline_metrics, cost_usd, duration_ms.
        """
        sio = context._sio
        dataset_id = context.dataset_id
        results = task_results or {}

        # ── Per-agent metrics ─────────────────────────────────────────────
        for result in results.values():
            self._emitter.emit_agent_metrics(result)

            # Alert on slow agents
            if result.duration_ms > SLOW_AGENT_THRESHOLD_MS and sio and dataset_id:
                with contextlib.suppress(Exception):
                    await sio.emit(
                        "monitoring:agent_slow",
                        {
                            "dataset_id": dataset_id,
                            "agent": result.agent_name,
                            "duration_ms": result.duration_ms,
                            "threshold_ms": SLOW_AGENT_THRESHOLD_MS,
                        },
                        room=f"dataset:{dataset_id}",
                    )

        # ── Pipeline-level metrics ────────────────────────────────────────
        total_ms = int((time.monotonic() - start_time) * 1000) if start_time else 0
        cost_usd = context.get("total_cost_usd", 0.0)
        succeeded = sum(1 for r in results.values() if r.success)
        failed = len(results) - succeeded

        self._emitter.emit_pipeline_metrics(
            dataset_id=dataset_id,
            succeeded=succeeded,
            failed=failed,
            total_ms=total_ms,
            cost_usd=cost_usd,
        )

        # ── OTel span event ───────────────────────────────────────────────
        add_span_event(
            "pipeline_complete",
            {
                "succeeded": succeeded,
                "failed": failed,
                "total_ms": total_ms,
                "cost_usd": cost_usd,
            },
        )

        # ── Cost alert ────────────────────────────────────────────────────
        if cost_usd >= COST_ALERT_THRESHOLD and sio and dataset_id:
            with contextlib.suppress(Exception):
                await sio.emit(
                    "monitoring:cost_alert",
                    {
                        "dataset_id": dataset_id,
                        "cost_usd": cost_usd,
                        "threshold": COST_ALERT_THRESHOLD,
                    },
                    room=f"dataset:{dataset_id}",
                )

        # ── Persist agent execution audit log (non-blocking) ─────────────
        asyncio.ensure_future(self._persist_audit_log(context, results, total_ms, cost_usd))

        # ── Emit monitoring:pipeline_report to admin room ─────────────────
        report = {
            "dataset_id": dataset_id,
            "session_id": context.session_id,
            "succeeded": succeeded,
            "failed": failed,
            "total_ms": total_ms,
            "cost_usd": round(cost_usd, 6),
            "total_tokens": context.get("total_tokens", 0),
            "agent_timings": [
                {
                    "agent": r.agent_name,
                    "duration_ms": r.duration_ms,
                    "tokens": r.total_tokens,
                    "cost_usd": r.estimated_cost_usd,
                    "success": r.success,
                }
                for r in results.values()
            ],
        }

        if sio and dataset_id:
            try:
                await sio.emit(
                    "monitoring:pipeline_report",
                    report,
                    room=f"monitoring:{dataset_id}",  # separate admin room
                )
            except Exception as exc:
                logger.debug("monitoring_report_emit_failed", error=str(exc))

        logger.info(
            "monitoring_complete",
            session_id=context.session_id,
            duration_ms=total_ms,
            cost_usd=round(cost_usd, 6),
            succeeded=succeeded,
            failed=failed,
        )
        return report

    @staticmethod
    async def _persist_audit_log(
        context: AgentContext,
        results: dict[str, AgentResult],
        total_ms: int,
        cost_usd: float,
    ) -> None:
        """Write agent execution records to Postgres audit table (non-blocking)."""
        try:
            from datetime import datetime

            from backend.infrastructure.persistence.database import get_session
            from backend.infrastructure.persistence.models.agent_execution_model import (
                AgentExecutionModel,
            )
            from backend.shared.utils.uuid_factory import new_uuid

            async with get_session() as db_session:
                for result in results.values():
                    record = AgentExecutionModel(
                        id=new_uuid(),
                        agent_name=result.agent_name,
                        session_id=context.session_id,
                        success=result.success,
                        duration_ms=result.duration_ms,
                        token_count=result.total_tokens,
                        cost_usd=result.estimated_cost_usd,
                        model_id=result.model_id or "",
                        error=result.error,
                        created_at=datetime.now(UTC),
                    )
                    db_session.add(record)
        except Exception as exc:
            logger.debug("audit_log_persist_failed", error=str(exc))
