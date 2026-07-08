"""TaskNode entity — one node in an agent execution DAG."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from backend.shared.entity import Entity


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    SKIPPED = "skipped"  # dependency failed; task was bypassed


class AgentRole(StrEnum):
    """Every agent name the Planner can schedule in an ExecutionPlan.

    Must match the keys in the agent_registry dict passed to DAGExecutor.
    """

    SCHEMA = "schema"
    PROFILING = "profiling"
    CLEANING = "cleaning"
    RAG = "rag"
    SQL = "sql"
    PYTHON = "python"
    FORECAST = "forecast"
    ML = "ml"
    VISUALIZATION = "visualization"
    INSIGHT = "insight"
    CRITIC = "critic"
    RECOMMENDATION = "recommendation"
    REPORT = "report"
    VALIDATION = "validation"
    SECURITY = "security"
    MONITORING = "monitoring"


@dataclass
class TaskNode(Entity):
    """One scheduled agent task within an ExecutionPlan DAG.

    The Planner Agent creates a set of TaskNodes and links them via
    ``depends_on`` to express execution ordering. The DAGExecutor reads
    these links to run independent tasks in parallel using ``asyncio.gather``.

    Attributes:
        plan_id:     Parent ExecutionPlan identifier.
        agent:       The agent role to execute (matches agent_registry key).
        depends_on:  IDs of TaskNodes that must complete before this one starts.
        priority:    Lower number = higher priority within the same parallel batch.
        status:      Current execution status.
        config:      Agent-specific configuration overrides passed at runtime.
                     Example: ``{'question': 'What are the top 10 rows?', 'row_limit': 500}``
        result_key:  Key under which the agent's output is stored in AgentContext.
                     Defaults to the agent role name.
        duration_ms: Wall-clock execution time. Set when status → COMPLETE/FAILED.
        error:       Error message. Set when status → FAILED.
    """

    plan_id: str
    agent: AgentRole
    depends_on: list[str] = field(default_factory=list)
    priority: int = 1
    status: TaskStatus = TaskStatus.PENDING
    config: dict = field(default_factory=dict)
    result_key: str = ""
    duration_ms: int | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if not self.result_key:
            self.result_key = self.agent.value

    # ── State transitions ─────────────────────────────────────────────────

    def mark_running(self) -> None:
        self.status = TaskStatus.RUNNING

    def mark_complete(self, duration_ms: int) -> None:
        self.status = TaskStatus.COMPLETE
        self.duration_ms = duration_ms

    def mark_failed(self, error: str, duration_ms: int | None = None) -> None:
        self.status = TaskStatus.FAILED
        self.error = error
        self.duration_ms = duration_ms

    def mark_skipped(self) -> None:
        self.status = TaskStatus.SKIPPED

    # ── Derived helpers ───────────────────────────────────────────────────

    @property
    def is_ready(self) -> bool:
        """True when status is PENDING — has not been dispatched yet."""
        return self.status == TaskStatus.PENDING

    @property
    def is_terminal(self) -> bool:
        return self.status in (TaskStatus.COMPLETE, TaskStatus.FAILED, TaskStatus.SKIPPED)

    @property
    def succeeded(self) -> bool:
        return self.status == TaskStatus.COMPLETE

    def can_run(self, completed_task_ids: set[str]) -> bool:
        """True when all dependencies have successfully completed."""
        return all(dep in completed_task_ids for dep in self.depends_on)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "plan_id": self.plan_id,
            "agent": self.agent.value,
            "depends_on": self.depends_on,
            "priority": self.priority,
            "status": self.status.value,
            "config": self.config,
            "result_key": self.result_key,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }
