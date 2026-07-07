"""OrchestratorAgent — drives the full analysis pipeline DAG.

Real-time design:
    The OrchestratorAgent is the top-level coordinator for an analysis run.
    It accepts a pre-built ExecutionPlan from PlannerAgent, executes it via
    DAGExecutor, aggregates results, and emits ``analysis.complete`` to the
    dataset's Socket.IO room.

    For the LangGraph integration, individual LangGraph nodes call specific
    agents directly (SchemaNode → SchemaAgent, etc.) rather than using the
    OrchestratorAgent. The OrchestratorAgent is used for batch runs triggered
    from Celery tasks where the full pipeline runs outside LangGraph.
"""
from __future__ import annotations

from typing import Any

import structlog
from backend.agents.base.agent_context import AgentContext
from backend.agents.base.base_agent import BaseAgent
from backend.agents.control.orchestrator.dag_executor import DAGExecutor
from backend.agents.control.orchestrator.result_aggregator import ResultAggregator

logger = structlog.get_logger(__name__)


class OrchestratorAgent(BaseAgent):
    """Executes an ExecutionPlan DAG and aggregates results into AgentContext.

    Args:
        agent_registry: Dict mapping agent name strings to agent instances.
                        Example: {"schema": SchemaAgent(), "sql": SQLAgent(...)}
    """

    def __init__(self, agent_registry: dict) -> None:
        super().__init__("orchestrator")
        self._executor   = DAGExecutor(agent_registry)
        self._aggregator = ResultAggregator()

    async def _execute(
        self,
        context: AgentContext,
        plan=None,
        **kwargs: Any,
    ) -> dict:
        """Execute the plan DAG and return an aggregated results summary.

        Args:
            context: Shared mutable pipeline state.
            plan:    ExecutionPlan from PlannerAgent. Required.

        Returns:
            Dict with keys: succeeded, failed, total_tokens, cost_usd,
            agent_summary (list of per-agent result dicts).
        """
        if plan is None:
            raise ValueError(
                "OrchestratorAgent requires a plan argument. "
                "Call: await orchestrator.run(context, plan=execution_plan)"
            )

        logger.info(
            "orchestration_start",
            plan_id=getattr(plan, "plan_id", "?"),
            task_count=len(getattr(plan, "tasks", [])),
            session_id=context.session_id,
        )

        # Execute all DAG tasks
        task_results = await self._executor.execute(plan, context)

        # Merge results into the shared context
        context = self._aggregator.aggregate(task_results, context)

        # Build summary
        succeeded = [r for r in task_results.values() if r.success]
        failed    = [r for r in task_results.values() if not r.success]

        summary = {
            "succeeded":     len(succeeded),
            "failed":        len(failed),
            "total_tasks":   len(task_results),
            "total_tokens":  context.get("total_tokens", 0),
            "cost_usd":      context.get("total_cost_usd", 0.0),
            "agent_summary": [r.to_ws_event() for r in task_results.values()],
        }

        # Emit analysis.complete to the Socket.IO room
        await context.push_progress(
            100,
            "Analysis complete",
            step="complete",
            extra=summary,
        )
        if context._sio:
            try:
                await context._sio.emit(
                    "analysis.complete",
                    {
                        "dataset_id":    context.dataset_id,
                        "session_id":    context.session_id,
                        "insight_count": len(context.insight_results),
                        **summary,
                    },
                    room=f"dataset:{context.dataset_id}",
                )
            except Exception:
                pass

        logger.info(
            "orchestration_complete",
            succeeded=len(succeeded),
            failed=len(failed),
            cost_usd=round(summary["cost_usd"], 4),
        )
        return summary
