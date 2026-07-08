"""ExecutionPlan schema — typed DAG structure output by PlannerAgent.

Designed for real-time visibility: every TaskNode has a status field
that the OrchestratorAgent updates as tasks progress. The frontend can
request the plan structure to render a live pipeline progress indicator
showing which agents are pending, running, succeeded, or failed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from backend.shared.utils.uuid_factory import new_uuid
from pydantic import BaseModel, Field


class AgentName(StrEnum):
    """Enumeration of all valid agent names in the execution plan."""

    SCHEMA = "schema"
    PROFILING = "profiling"
    CLEANING = "cleaning"
    SQL = "sql"
    PYTHON = "python"
    FORECAST = "forecast"
    ML = "ml"
    VISUALIZATION = "visualization"
    ANOMALY = "anomaly"
    INSIGHT = "insight"
    CRITIC = "critic"
    RECOMMENDATION = "recommendation"
    REPORT = "report"
    RAG = "rag"
    VALIDATION = "validation"
    MONITORING = "monitoring"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class PlanStatus(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class TaskNode(BaseModel):
    """One task in the execution plan DAG."""

    task_id: str
    agent: AgentName
    depends_on: list[str] = Field(default_factory=list)
    priority: int = 1
    config: dict[str, Any] = Field(default_factory=dict)

    # Runtime state (updated by DAGExecutor)
    status: TaskStatus = TaskStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None

    def mark_running(self) -> None:
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now(UTC)

    def mark_succeeded(self) -> None:
        self.status = TaskStatus.SUCCEEDED
        self.finished_at = datetime.now(UTC)

    def mark_failed(self, error: str) -> None:
        self.status = TaskStatus.FAILED
        self.error = error
        self.finished_at = datetime.now(UTC)

    def mark_skipped(self) -> None:
        self.status = TaskStatus.SKIPPED

    @property
    def duration_ms(self) -> int | None:
        if self.started_at and self.finished_at:
            return int((self.finished_at - self.started_at).total_seconds() * 1000)
        return None


class ExecutionPlan(BaseModel):
    """Full DAG execution plan produced by PlannerAgent."""

    plan_id: str = Field(default_factory=new_uuid)
    session_id: str = ""
    dataset_id: str = ""
    trigger: str = "dataset_ready"
    tasks: list[TaskNode] = Field(default_factory=list)
    estimated_duration_seconds: int = 30
    status: PlanStatus = PlanStatus.DRAFT
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # ── DAG traversal ─────────────────────────────────────────────────────

    def get_ready_tasks(self, completed_ids: set[str]) -> list[TaskNode]:
        """Return tasks whose dependencies are all in completed_ids."""
        return [
            t
            for t in self.tasks
            if t.status == TaskStatus.PENDING and all(dep in completed_ids for dep in t.depends_on)
        ]

    def begin(self) -> None:
        self.status = PlanStatus.RUNNING

    def record_task_complete(self, task_id: str, duration_ms: int = 0) -> None:
        task = self._get_task(task_id)
        if task:
            task.mark_succeeded()

    def record_task_failed(self, task_id: str, error: str = "") -> None:
        task = self._get_task(task_id)
        if task:
            task.mark_failed(error)
            # Skip all dependents
            self._skip_descendants(task_id)

    def _skip_descendants(self, failed_id: str) -> None:
        for task in self.tasks:
            if failed_id in task.depends_on and task.status == TaskStatus.PENDING:
                task.mark_skipped()
                self._skip_descendants(task.task_id)

    def _get_task(self, task_id: str) -> TaskNode | None:
        return next((t for t in self.tasks if t.task_id == task_id), None)

    @property
    def is_complete(self) -> bool:
        return all(
            t.status in (TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.SKIPPED)
            for t in self.tasks
        )

    def validate(self) -> None:
        """Raise ValueError if the DAG has cycles or unknown dependencies."""
        task_ids = {t.task_id for t in self.tasks}
        for task in self.tasks:
            for dep in task.depends_on:
                if dep not in task_ids:
                    raise ValueError(f"Task {task.task_id!r} depends on unknown task {dep!r}")
        # Topological sort to detect cycles
        self._topo_sort()

    def _topo_sort(self) -> list[str]:
        in_degree = {t.task_id: len(t.depends_on) for t in self.tasks}
        adj: dict[str, list[str]] = {t.task_id: [] for t in self.tasks}
        for task in self.tasks:
            for dep in task.depends_on:
                if dep in adj:
                    adj[dep].append(task.task_id)

        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        order = []
        while queue:
            tid = queue.pop(0)
            order.append(tid)
            for neighbour in adj.get(tid, []):
                in_degree[neighbour] -= 1
                if in_degree[neighbour] == 0:
                    queue.append(neighbour)

        if len(order) != len(self.tasks):
            raise ValueError("ExecutionPlan contains a cycle in the DAG")
        return order

    # ── Factories ─────────────────────────────────────────────────────────

    @classmethod
    def create_default(
        cls,
        plan_id: str = "",
        session_id: str = "",
        dataset_id: str = "",
        has_datetime: bool = False,
        numeric_cols: int = 0,
    ) -> ExecutionPlan:
        """Build a sensible default plan without calling the LLM.

        Used as the fallback when PlannerAgent fails to parse the LLM response.
        """
        tasks = [
            TaskNode(task_id="t_schema", agent=AgentName.SCHEMA, depends_on=[]),
            TaskNode(task_id="t_profile", agent=AgentName.PROFILING, depends_on=["t_schema"]),
            TaskNode(task_id="t_clean", agent=AgentName.CLEANING, depends_on=["t_profile"]),
            TaskNode(task_id="t_sql", agent=AgentName.SQL, depends_on=["t_clean"]),
            TaskNode(task_id="t_rag", agent=AgentName.RAG, depends_on=["t_profile"]),
        ]

        parallel_deps = ["t_sql", "t_rag"]

        if has_datetime:
            tasks.append(
                TaskNode(task_id="t_forecast", agent=AgentName.FORECAST, depends_on=["t_clean"])
            )
            parallel_deps.append("t_forecast")

        if numeric_cols >= 5:
            tasks.append(TaskNode(task_id="t_ml", agent=AgentName.ML, depends_on=["t_clean"]))
            parallel_deps.append("t_ml")

        tasks += [
            TaskNode(task_id="t_insight", agent=AgentName.INSIGHT, depends_on=parallel_deps),
            TaskNode(task_id="t_critic", agent=AgentName.CRITIC, depends_on=["t_insight"]),
            TaskNode(task_id="t_rec", agent=AgentName.RECOMMENDATION, depends_on=["t_critic"]),
            TaskNode(task_id="t_report", agent=AgentName.REPORT, depends_on=["t_rec"]),
        ]

        return cls(
            plan_id=plan_id or new_uuid(),
            session_id=session_id,
            dataset_id=dataset_id,
            trigger="dataset_ready",
            tasks=tasks,
            estimated_duration_seconds=45
            + (15 if has_datetime else 0)
            + (20 if numeric_cols >= 5 else 0),
        )

    def to_ws_event(self) -> dict:
        """Serialise the plan for a Socket.IO ``plan:ready`` event."""
        return {
            "plan_id": self.plan_id,
            "dataset_id": self.dataset_id,
            "task_count": len(self.tasks),
            "tasks": [
                {
                    "task_id": t.task_id,
                    "agent": t.agent.value,
                    "depends_on": t.depends_on,
                    "status": t.status.value,
                }
                for t in self.tasks
            ],
            "estimated_duration_s": self.estimated_duration_seconds,
        }
