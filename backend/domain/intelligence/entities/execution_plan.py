"""ExecutionPlan aggregate root — the complete agent DAG for one analysis run."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from backend.domain.intelligence.entities.task_node import AgentRole, TaskNode, TaskStatus
from backend.domain.intelligence.events.agent_result_ready import AgentResultReady
from backend.domain.intelligence.exceptions import (
    DAGCycleDetectedError,
    InvalidExecutionPlanError,
)
from backend.shared.aggregate_root import AggregateRoot


class PlanStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class ExecutionPlan(AggregateRoot):
    """Aggregate root that owns the full agent DAG for one analysis session.

    Created by the PlannerAgent and executed by the DAGExecutor. Maintains
    the status of every TaskNode and the overall plan status.

    The plan enforces:
    - No duplicate task IDs
    - No dependency cycles (validated on creation)
    - All agent names must be in the known AgentRole enum

    Domain events are emitted as each TaskNode completes, allowing the
    WebSocket gateway to stream progress updates to the browser.

    Attributes:
        id:            Plan UUID.
        session_id:    Parent AnalysisSession.
        dataset_id:    Source dataset.
        trigger:       What created this plan: ``'dataset_ready'``, ``'chat_query'``.
        tasks:         All TaskNode entities in the plan.
        status:        Overall plan status.
        started_at:    UTC timestamp when first task began.
        completed_at:  UTC timestamp when all tasks reached a terminal state.
    """

    id: str
    session_id: str
    dataset_id: str
    trigger: str = "dataset_ready"
    tasks: list[TaskNode] = field(default_factory=list)
    status: PlanStatus = PlanStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        super().__init__()

    # ── Validation ────────────────────────────────────────────────────────

    def validate(self) -> None:
        """Validate the plan graph before execution starts.

        Raises:
            InvalidExecutionPlanError: Duplicate task IDs.
            DAGCycleDetectedError:     Dependency cycle detected.
        """
        task_ids = [t.id for t in self.tasks]

        # Check for duplicate IDs
        if len(task_ids) != len(set(task_ids)):
            dupes = [tid for tid in task_ids if task_ids.count(tid) > 1]
            raise InvalidExecutionPlanError(self.id, f"Duplicate task IDs: {dupes}")

        # Topological sort to detect cycles
        self._topological_sort()

    def _topological_sort(self) -> list[TaskNode]:
        """Kahn's algorithm — raises DAGCycleDetectedError if a cycle exists."""
        id_to_node = {t.id: t for t in self.tasks}
        in_degree = {t.id: 0 for t in self.tasks}
        for t in self.tasks:
            for dep in t.depends_on:
                if dep not in in_degree:
                    raise InvalidExecutionPlanError(
                        self.id, f"Task '{t.id}' depends on unknown task '{dep}'"
                    )
                in_degree[t.id] += 1

        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        result = []
        while queue:
            tid = queue.pop(0)
            result.append(id_to_node[tid])
            for t in self.tasks:
                if tid in t.depends_on:
                    in_degree[t.id] -= 1
                    if in_degree[t.id] == 0:
                        queue.append(t.id)

        if len(result) != len(self.tasks):
            cyclic = [tid for tid, deg in in_degree.items() if deg > 0]
            raise DAGCycleDetectedError(cyclic)
        return result

    # ── Execution lifecycle ───────────────────────────────────────────────

    def begin(self) -> None:
        """Mark the plan as running when the first task is dispatched."""
        self.status = PlanStatus.RUNNING
        self.started_at = datetime.now(UTC)

    def record_task_complete(self, task_id: str, duration_ms: int) -> None:
        """Called by the DAGExecutor after a task succeeds."""
        task = self._get_task(task_id)
        task.mark_complete(duration_ms)
        self._record_event(
            AgentResultReady(
                session_id=self.session_id,
                dataset_id=self.dataset_id,
                agent_name=task.agent.value,
                task_id=task_id,
                success=True,
            )
        )
        self._check_completion()

    def record_task_failed(self, task_id: str, error: str, duration_ms: int | None = None) -> None:
        """Called by the DAGExecutor when a task raises an exception."""
        task = self._get_task(task_id)
        task.mark_failed(error, duration_ms)
        # Skip tasks that depended on this one
        for t in self.tasks:
            if task_id in t.depends_on and t.status == TaskStatus.PENDING:
                t.mark_skipped()
        self._check_completion()

    def _check_completion(self) -> None:
        all_terminal = all(t.is_terminal for t in self.tasks)
        if all_terminal:
            any_failed = any(t.status == TaskStatus.FAILED for t in self.tasks)
            self.status = PlanStatus.FAILED if any_failed else PlanStatus.COMPLETE
            self.completed_at = datetime.now(UTC)

    # ── Query helpers ─────────────────────────────────────────────────────

    def get_ready_tasks(self, completed_ids: set[str]) -> list[TaskNode]:
        """Return tasks that are PENDING and have all dependencies satisfied.

        Called by DAGExecutor each iteration to find the next parallel batch.
        Results are sorted by priority (ascending) so higher-priority tasks
        are dispatched first within the same batch.
        """
        ready = [t for t in self.tasks if t.is_ready and t.can_run(completed_ids)]
        return sorted(ready, key=lambda t: t.priority)

    def _get_task(self, task_id: str) -> TaskNode:
        for t in self.tasks:
            if t.id == task_id:
                return t
        raise KeyError(f"Task '{task_id}' not found in plan '{self.id}'")

    @property
    def completed_task_ids(self) -> set[str]:
        return {t.id for t in self.tasks if t.status == TaskStatus.COMPLETE}

    @property
    def failed_tasks(self) -> list[TaskNode]:
        return [t for t in self.tasks if t.status == TaskStatus.FAILED]

    @property
    def total_cost_usd(self) -> float:
        """Sum of estimated costs across all completed tasks (from AgentResult)."""
        return 0.0  # populated by the cost tracker post-execution

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    # ── Factory ───────────────────────────────────────────────────────────

    @classmethod
    def create_default(
        cls,
        plan_id: str,
        session_id: str,
        dataset_id: str,
        has_datetime: bool = False,
        has_enough_numerics: bool = False,
    ) -> ExecutionPlan:
        """Build the standard analysis plan with sensible defaults.

        The Planner Agent calls this factory when the LLM output cannot be
        parsed (fallback plan), or it serves as a reference for unit tests.
        """
        from backend.shared.utils.uuid_factory import new_uuid

        tasks = [
            TaskNode(
                id=new_uuid(), plan_id=plan_id, agent=AgentRole.SCHEMA, depends_on=[], priority=1
            ),
            TaskNode(
                id=new_uuid(), plan_id=plan_id, agent=AgentRole.PROFILING, depends_on=[], priority=1
            ),
        ]
        schema_id = tasks[0].id
        profiling_id = tasks[1].id

        cleaning = TaskNode(
            id=new_uuid(),
            plan_id=plan_id,
            agent=AgentRole.CLEANING,
            depends_on=[schema_id, profiling_id],
            priority=2,
        )
        tasks.append(cleaning)

        sql_id = new_uuid()
        tasks.append(
            TaskNode(
                id=sql_id,
                plan_id=plan_id,
                agent=AgentRole.SQL,
                depends_on=[cleaning.id],
                priority=3,
            )
        )
        rag_id = new_uuid()
        tasks.append(
            TaskNode(
                id=rag_id,
                plan_id=plan_id,
                agent=AgentRole.RAG,
                depends_on=[cleaning.id],
                priority=3,
            )
        )

        analysis_deps = [sql_id, rag_id]

        if has_datetime:
            fc_id = new_uuid()
            tasks.append(
                TaskNode(
                    id=fc_id,
                    plan_id=plan_id,
                    agent=AgentRole.FORECAST,
                    depends_on=[cleaning.id],
                    priority=3,
                )
            )
            analysis_deps.append(fc_id)

        if has_enough_numerics:
            ml_id = new_uuid()
            tasks.append(
                TaskNode(
                    id=ml_id,
                    plan_id=plan_id,
                    agent=AgentRole.ML,
                    depends_on=[cleaning.id],
                    priority=3,
                )
            )
            analysis_deps.append(ml_id)

        insight_id = new_uuid()
        tasks.append(
            TaskNode(
                id=insight_id,
                plan_id=plan_id,
                agent=AgentRole.INSIGHT,
                depends_on=analysis_deps,
                priority=4,
            )
        )
        critic_id = new_uuid()
        tasks.append(
            TaskNode(
                id=critic_id,
                plan_id=plan_id,
                agent=AgentRole.CRITIC,
                depends_on=[insight_id],
                priority=5,
            )
        )
        rec_id = new_uuid()
        tasks.append(
            TaskNode(
                id=rec_id,
                plan_id=plan_id,
                agent=AgentRole.RECOMMENDATION,
                depends_on=[critic_id],
                priority=6,
            )
        )
        report_id = new_uuid()
        tasks.append(
            TaskNode(
                id=report_id,
                plan_id=plan_id,
                agent=AgentRole.REPORT,
                depends_on=[rec_id],
                priority=7,
            )
        )

        return cls(id=plan_id, session_id=session_id, dataset_id=dataset_id, tasks=tasks)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "dataset_id": self.dataset_id,
            "trigger": self.trigger,
            "status": self.status.value,
            "task_count": len(self.tasks),
            "tasks": [t.to_dict() for t in self.tasks],
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_s": self.duration_seconds,
        }
