"""PlannerAgent — decomposes pipeline triggers into an ExecutionPlan DAG.

Real-time design:
    After generating the plan, the agent emits a ``plan:ready`` Socket.IO
    event to the dataset's room. The frontend renders a live pipeline
    topology diagram so users can see which agents are about to run before
    execution begins.

Plan generation:
    1. Build a schema summary from AgentContext.schema
    2. Call Claude Sonnet with a structured JSON prompt
    3. Parse the response into ExecutionPlan
    4. Fall back to create_default() if parsing fails
    5. Validate the DAG for cycles and unknown dependencies
    6. Emit plan:ready via Socket.IO
"""

from __future__ import annotations

import contextlib
import json
import re
from typing import Any

import structlog
from backend.agents.base.agent_context import AgentContext
from backend.agents.base.base_agent import BaseAgent
from backend.agents.control.planner.plan_schema import AgentName, ExecutionPlan
from backend.infrastructure.llm.model_id_registry import get_model_id
from backend.shared.utils.uuid_factory import new_uuid

logger = structlog.get_logger(__name__)

_SYSTEM = (
    "You are a DataPilot pipeline planner. "
    "Return ONLY valid JSON matching the ExecutionPlan schema. "
    "No explanation. No markdown."
)


class PlannerAgent(BaseAgent):
    """Calls Claude Sonnet to produce an ExecutionPlan JSON object.

    Args:
        llm_client: Async LLM client (Claude Sonnet for planning quality).
    """

    def __init__(self, llm_client: Any) -> None:  # noqa: ANN401
        super().__init__("planner")
        self._llm = llm_client

    async def _execute(
        self,
        context: AgentContext,
        trigger: str = "dataset_ready",
        **kwargs: Any,  # noqa: ANN401
    ) -> dict:
        """Generate an ExecutionPlan for the given trigger.

        Args:
            context: Shared pipeline state (schema used for routing decisions).
            trigger: Why the pipeline is being run (dataset_ready, user_request, etc.)

        Returns:
            ExecutionPlan.to_ws_event() dict (also stored in context.metadata).
        """
        schema_summary, has_datetime, numeric_count = self._analyse_schema(context)

        prompt = self._build_prompt(
            trigger=trigger,
            dataset_id=context.dataset_id,
            schema_summary=schema_summary,
            has_datetime=has_datetime,
            numeric_count=numeric_count,
        )

        plan = await self._generate_plan(
            prompt=prompt,
            session_id=context.session_id,
            dataset_id=context.dataset_id,
            has_datetime=has_datetime,
            numeric_count=numeric_count,
        )

        # Validate before storing
        try:
            plan.validate()
        except ValueError as exc:
            logger.warning("plan_validation_failed", error=str(exc))
            plan = ExecutionPlan.create_default(
                plan_id=plan.plan_id,
                session_id=context.session_id,
                dataset_id=context.dataset_id,
                has_datetime=has_datetime,
                numeric_cols=numeric_count,
            )

        # Store in context for the orchestrator
        context.set("execution_plan", plan)

        # Emit plan:ready to Socket.IO so frontend can render the pipeline graph
        ws_payload = plan.to_ws_event()
        if context._sio:
            with contextlib.suppress(Exception):
                await context._sio.emit(
                    "plan:ready",
                    {**ws_payload, "correlation_id": context.correlation_id},
                    room=f"dataset:{context.dataset_id}",
                )

        logger.info(
            "plan_generated",
            plan_id=plan.plan_id,
            task_count=len(plan.tasks),
            has_forecast="t_forecast" in {t.task_id for t in plan.tasks},
            has_ml="t_ml" in {t.task_id for t in plan.tasks},
        )
        return ws_payload

    async def _generate_plan(
        self,
        prompt: str,
        session_id: str,
        dataset_id: str,
        has_datetime: bool,
        numeric_count: int,
    ) -> ExecutionPlan:
        """Call the LLM and parse the result into an ExecutionPlan."""
        try:
            raw = await self._llm.complete(
                prompt=prompt,
                system=_SYSTEM,
                model_id=get_model_id("planner"),
                max_tokens=1500,
            )
            data = self._parse_json(raw)
            if data and "tasks" in data:
                data.setdefault("plan_id", new_uuid())
                data.setdefault("session_id", session_id)
                data.setdefault("dataset_id", dataset_id)
                # Validate task agent names
                valid_agents = {a.value for a in AgentName}
                for task in data["tasks"]:
                    if task.get("agent") not in valid_agents:
                        raise ValueError(f"Unknown agent: {task.get('agent')}")
                return ExecutionPlan(**data)
        except Exception as exc:
            logger.warning("planner_llm_parse_failed", error=str(exc))

        # Fallback: static default plan
        return ExecutionPlan.create_default(
            session_id=session_id,
            dataset_id=dataset_id,
            has_datetime=has_datetime,
            numeric_cols=numeric_count,
        )

    @staticmethod
    def _analyse_schema(context: AgentContext) -> tuple[str, bool, int]:
        """Extract schema statistics for the planner prompt."""
        if not context.schema:
            return "Schema not yet available.", False, 0

        cols = context.schema.get("columns", [])
        has_datetime = any(c.get("semantic_type") in ("date", "datetime") for c in cols)
        numeric = {"currency", "numeric_measure", "numeric_count", "percentage"}
        num_count = sum(1 for c in cols if c.get("semantic_type") in numeric)

        col_lines = "\n".join(
            f"  {c['name']} ({c.get('semantic_type', c.get('data_type', '?'))})" for c in cols[:15]
        )
        summary = (
            f"{len(cols)} columns; "
            f"has_datetime={has_datetime}; "
            f"numeric_columns={num_count}\n"
            f"Column sample:\n{col_lines}"
        )
        return summary, has_datetime, num_count

    @staticmethod
    def _build_prompt(
        trigger: str,
        dataset_id: str,
        schema_summary: str,
        has_datetime: bool,
        numeric_count: int,
    ) -> str:
        return f"""Create an ExecutionPlan JSON for this analytics pipeline.

TRIGGER: {trigger}
DATASET ID: {dataset_id}
SCHEMA: {schema_summary}

ROUTING RULES:
- schema → profiling → cleaning (always sequential)
- sql, rag run in parallel after cleaning (depends_on: ["t_clean"])
- forecast: ONLY if has_datetime={has_datetime} (depends_on: ["t_clean"])
- ml: ONLY if numeric_columns >= 5 (current: {numeric_count}) (depends_on: ["t_clean"])
- insight depends on all parallel tasks
- critic → recommendation → report (always sequential after insight)

Return ONLY valid JSON:
{{
  "plan_id": "{new_uuid()}",
  "dataset_id": "{dataset_id}",
  "trigger": "{trigger}",
  "estimated_duration_seconds": 45,
  "tasks": [
    {{"task_id": "t_schema", "agent": "schema", "depends_on": [], "priority": 1, "config": {{}}}},
    {{"task_id": "t_profile", "agent": "profiling", "depends_on": ["t_schema"],
     "priority": 1, "config": {{}}}},
    {{"task_id": "t_clean", "agent": "cleaning", "depends_on": ["t_profile"],
     "priority": 1, "config": {{}}}},
    {{"task_id": "t_sql", "agent": "sql", "depends_on": ["t_clean"],
     "priority": 2, "config": {{}}}},
    {{"task_id": "t_rag", "agent": "rag", "depends_on": ["t_profile"], "priority": 2,
     "config": {{"index_dataset": true}}}},
    {{"task_id": "t_insight", "agent": "insight", "depends_on": ["t_sql","t_rag"], "priority": 3,
     "config": {{}}}},
    {{"task_id": "t_critic", "agent": "critic", "depends_on": ["t_insight"],
     "priority": 4, "config": {{}}}},
    {{"task_id": "t_rec", "agent": "recommendation", "depends_on": ["t_critic"], "priority": 5,
     "config": {{}}}},
    {{"task_id": "t_report", "agent": "report", "depends_on": ["t_rec"],
     "priority": 6, "config": {{}}}}
  ]
}}"""

    @staticmethod
    def _parse_json(raw: str) -> dict | None:
        """Extract and parse a JSON object from an LLM response string."""
        text = raw.strip()
        # Strip markdown fences
        if text.startswith("```"):
            text = "\n".join(
                line for line in text.splitlines() if not line.startswith("``")
            ).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        return None
