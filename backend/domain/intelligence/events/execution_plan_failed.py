"""ExecutionPlanFailed domain event."""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.shared.domain_event import DomainEvent


@dataclass(frozen=True)
class ExecutionPlanFailed(DomainEvent):
    """Emitted by ``ExecutionPlan._check_completion()`` when any task in the
    plan reaches a terminal FAILED state.

    Consumed by:
    - WebSocket gateway — surfaces a pipeline-failure banner to the browser
    - MonitoringAgent — records failure telemetry to Prometheus
    - Audit logger — writes the failure reason to the append-only audit table
    """

    plan_id: str = ""
    session_id: str = ""
    dataset_id: str = ""
    failed_task_ids: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update(
            {
                "plan_id": self.plan_id,
                "session_id": self.session_id,
                "dataset_id": self.dataset_id,
                "failed_task_ids": list(self.failed_task_ids),
                "reason": self.reason,
            }
        )
        return base
