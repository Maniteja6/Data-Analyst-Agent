"""ResultAggregator — merges DAG task results into the shared AgentContext.

After DAGExecutor completes all task waves, ResultAggregator maps each
AgentResult.payload into the correct AgentContext field so downstream
agents (InsightAgent, CriticAgent) see a fully-populated context object.

Real-time integration:
    After aggregation, the orchestrator emits a ``context:ready`` Socket.IO
    event so the frontend knows all parallel agents have completed and
    the insight generation phase is beginning.
"""
from __future__ import annotations

import structlog

from backend.agents.base.agent_context import AgentContext
from backend.agents.base.agent_result import AgentResult

logger = structlog.get_logger(__name__)

# Maps agent name → context field and how to merge (set/append)
_FIELD_MAP: dict[str, tuple[str, str]] = {
    "schema":         ("schema",          "set"),
    "profiling":      ("profile",         "set"),
    "cleaning":       ("cleaning_report", "set"),
    "sql":            ("sql_results",     "append"),
    "python":         ("python_results",  "append"),
    "forecast":       ("forecast_results","append"),
    "ml":             ("ml_results",      "set"),
    "anomaly":        ("anomaly_results", "extend"),
    "visualization":  ("visualization_specs", "append"),
    "insight":        ("insight_results", "extend"),
    "recommendation": ("recommendations", "extend"),
    "rag":            ("rag_context",     "set_text"),
    "critic":         ("insight_results", "extend_critique"),
}


class ResultAggregator:
    """Maps DAGExecutor results into AgentContext fields."""

    def aggregate(
        self,
        results: dict[str, AgentResult],
        context: AgentContext,
    ) -> AgentContext:
        """Merge all successful task results into the shared context.

        Args:
            results: Dict of task_id → AgentResult from DAGExecutor.
            context: Shared pipeline state to update in place.

        Returns:
            The updated AgentContext (same object, mutated).
        """
        successful = [(agent_name, r) for task_id, r in results.items()
                      if r.success and r.payload is not None
                      for agent_name in [r.agent_name]]

        for agent_name, result in successful:
            mapping = _FIELD_MAP.get(agent_name)
            if not mapping:
                context.set(f"result_{agent_name}", result.payload)
                continue

            field_name, merge_op = mapping
            self._merge(context, field_name, merge_op, result.payload, agent_name)

        # Record token and cost summary in metadata
        total_tokens = sum(r.total_tokens for r in results.values())
        total_cost   = sum(r.estimated_cost_usd for r in results.values())
        context.set("total_tokens",   total_tokens)
        context.set("total_cost_usd", total_cost)
        context.set("agent_results",  {r.agent_name: r.to_dict() for r in results.values()})

        logger.info(
            "results_aggregated",
            agents=len(successful),
            total_tokens=total_tokens,
            estimated_cost_usd=round(total_cost, 6),
        )
        return context

    @staticmethod
    def _merge(
        context:    AgentContext,
        field:      str,
        operation:  str,
        payload:    object,
        agent_name: str,
    ) -> None:
        """Apply the merge operation for one result into its context field."""
        try:
            if operation == "set":
                setattr(context, field, payload)

            elif operation == "append":
                lst = getattr(context, field, [])
                lst.append(payload)
                setattr(context, field, lst)

            elif operation == "extend":
                lst    = getattr(context, field, [])
                items  = payload if isinstance(payload, list) else [payload]
                lst.extend(items)
                setattr(context, field, lst)

            elif operation == "set_text":
                # RAG context: extract the text string from the payload
                if isinstance(payload, dict):
                    context.rag_context = payload.get("context", str(payload))
                else:
                    context.rag_context = str(payload)

            elif operation == "extend_critique":
                # Critic: apply revised_insights if the critique produced them
                if isinstance(payload, dict) and payload.get("revised_insights"):
                    context.insight_results = payload["revised_insights"]
                elif isinstance(payload, dict) and "insights" in payload:
                    insights = getattr(context, field, [])
                    insights.extend(payload["insights"])
                    setattr(context, field, insights)

        except Exception as exc:
            logger.warning(
                "result_merge_failed",
                agent=agent_name,
                field=field,
                error=str(exc),
            )
