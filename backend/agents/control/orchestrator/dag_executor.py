"""DAGExecutor — executes ExecutionPlan tasks with real-time Socket.IO progress events.

Real-time design:
    After each batch of parallel tasks completes, the executor emits a
    ``job:progress`` Socket.IO event to the dataset's room. This gives the
    browser live feedback as each wave of agents finishes — no polling needed.

Execution model:
    Tasks are sorted into topological waves (rounds). All tasks in a wave
    have their dependencies satisfied and run concurrently via asyncio.gather.
    Failed tasks are isolated — their dependents are marked SKIPPED so the
    pipeline produces partial results rather than aborting entirely.

Progress mapping:
    schema    → 5%    profiling → 20%    cleaning → 35%
    sql/py/forecast/ml → 50-70% (spread across the wave)
    insight   → 80%   critic → 90%      report → 100%
"""
from __future__ import annotations

import asyncio

import structlog
from backend.agents.base.agent_context import AgentContext
from backend.agents.base.agent_result import AgentResult
from backend.agents.control.planner.plan_schema import ExecutionPlan, TaskNode

logger = structlog.get_logger(__name__)

# Progress milestones by agent name
_PROGRESS: dict[str, int] = {
    "schema":         8,
    "profiling":      22,
    "cleaning":       38,
    "sql":            60,
    "python":         62,
    "forecast":       64,
    "ml":             66,
    "rag":            58,
    "visualization":  68,
    "anomaly":        70,
    "insight":        82,
    "critic":         90,
    "recommendation": 95,
    "report":        100,
}


class DAGExecutor:
    """Topological wave executor with real-time Socket.IO progress events.

    Args:
        agent_registry: Dict mapping agent name strings → agent instances.
    """

    def __init__(self, agent_registry: dict) -> None:
        self._registry = agent_registry

    async def execute(
        self,
        plan:    ExecutionPlan,
        context: AgentContext,
    ) -> dict[str, AgentResult]:
        """Execute all tasks in the plan, emitting progress after each wave.

        Args:
            plan:    ExecutionPlan from PlannerAgent.
            context: Shared mutable pipeline state.

        Returns:
            Dict mapping task_id → AgentResult for every attempted task.
        """
        completed: set[str]                = set()
        skipped:   set[str]                = set()
        results:   dict[str, AgentResult]  = {}
        pending:   list[TaskNode]          = list(plan.tasks)

        await context.push_progress(2, "Pipeline started", step="init")

        while pending:
            # Find tasks whose dependencies are all satisfied
            ready = [
                t for t in pending
                if t.task_id not in completed
                and t.task_id not in skipped
                and all(
                    dep in completed or dep in skipped
                    for dep in t.depends_on
                )
            ]

            if not ready:
                # Detect deadlock
                unblocked_count = len([
                    t for t in pending
                    if t.task_id not in completed and t.task_id not in skipped
                ])
                if unblocked_count > 0:
                    logger.error(
                        "dag_deadlock",
                        remaining=[t.task_id for t in pending
                                   if t.task_id not in completed and t.task_id not in skipped],
                    )
                break

            logger.info(
                "dag_wave_start",
                tasks=[t.task_id for t in ready],
                completed=len(completed),
                total=len(plan.tasks),
            )

            # Run this wave concurrently
            wave_results = await asyncio.gather(
                *[self._run_task(task, context) for task in ready],
                return_exceptions=True,
            )

            # Process results
            for task, result in zip(ready, wave_results):
                pending.remove(task)

                if isinstance(result, BaseException):
                    # Task failed — mark its dependents as skipped
                    error_str = str(result)
                    logger.error(
                        "dag_task_failed",
                        task_id=task.task_id,
                        agent=task.agent.value,
                        error=error_str,
                    )
                    results[task.task_id] = AgentResult(
                        agent_name=task.agent.value,
                        success=False,
                        error=error_str,
                    )
                    completed.add(task.task_id)

                    # Find and skip all descendants
                    self._skip_descendants(task.task_id, pending, skipped)

                else:
                    results[task.task_id] = result
                    completed.add(task.task_id)

                    # Emit real-time progress
                    progress = _PROGRESS.get(task.agent.value, 50)
                    await context.push_progress(
                        progress=progress,
                        message=f"{task.agent.value.title()} complete",
                        step=task.agent.value,
                        extra={"agent": task.agent.value},
                    )

                    # Emit agent:complete event for UI ticker
                    if context._sio:
                        try:
                            await context._sio.emit(
                                "agent:complete",
                                result.to_ws_event(),
                                room=f"dataset:{context.dataset_id}",
                            )
                        except Exception:
                            pass

        # Mark any remaining skipped tasks
        for task in pending:
            results[task.task_id] = AgentResult(
                agent_name=task.agent.value,
                success=False,
                error="Skipped due to upstream failure",
            )

        logger.info(
            "dag_complete",
            total=len(plan.tasks),
            succeeded=sum(1 for r in results.values() if r.success),
            failed=sum(1 for r in results.values() if not r.success),
        )
        return results

    async def _run_task(self, task: TaskNode, context: AgentContext) -> AgentResult:
        """Run a single task using the registered agent."""
        agent = self._registry.get(task.agent.value)
        if not agent:
            logger.warning("dag_missing_agent", agent=task.agent.value)
            return AgentResult(
                agent_name=task.agent.value,
                success=True,
                payload=None,
                error=f"Agent '{task.agent.value}' not registered",
            )

        await context.push_progress(
            progress=max(1, _PROGRESS.get(task.agent.value, 50) - 5),
            message=f"Running {task.agent.value}…",
            step=task.agent.value,
        )
        return await agent.run(context, **task.config)

    @staticmethod
    def _skip_descendants(
        failed_task_id: str,
        pending:        list[TaskNode],
        skipped:        set[str],
    ) -> None:
        """Recursively mark descendants of a failed task as skipped."""
        to_skip = {
            t.task_id for t in pending
            if failed_task_id in t.depends_on
        }
        for task_id in to_skip:
            if task_id not in skipped:
                skipped.add(task_id)
                DAGExecutor._skip_descendants(task_id, pending, skipped)
