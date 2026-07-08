"""ExecutionPlanCreated domain event."""

from __future__ import annotations

from dataclasses import dataclass

from backend.shared.domain_event import DomainEvent


@dataclass(frozen=True)
class ExecutionPlanCreated(DomainEvent):
    """Emitted by ``ExecutionPlan.create_default()`` once the agent DAG is built.

    Consumed by:
    - WebSocket gateway — tells the browser how many steps the pipeline
      will run, so the progress bar can render the right number of ticks
    - MonitoringAgent — records planned task count for telemetry
    """

    plan_id: str = ""
    session_id: str = ""
    dataset_id: str = ""
    trigger: str = ""
    task_count: int = 0

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update(
            {
                "plan_id": self.plan_id,
                "session_id": self.session_id,
                "dataset_id": self.dataset_id,
                "trigger": self.trigger,
                "task_count": self.task_count,
            }
        )
        return base
