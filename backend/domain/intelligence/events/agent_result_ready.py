"""AgentResultReady domain event."""

from __future__ import annotations

from dataclasses import dataclass

from backend.shared.domain_event import DomainEvent


@dataclass(frozen=True)
class AgentResultReady(DomainEvent):
    """Emitted by ``ExecutionPlan.record_task_complete()`` after each agent succeeds.

    Kafka topic: ``agent.result``

    Consumed by:
    - WebSocket gateway — pushes a step-completion progress tick to the browser's
      upload progress component, incrementing the active step indicator
    - MonitoringAgent — records agent execution telemetry to Prometheus
    - Audit logger — writes the agent name, token cost, and duration to the
      append-only audit table

    Emitting one event per agent (rather than one per pipeline) gives the
    browser fine-grained progress without requiring the frontend to poll.

    Attributes:
        session_id:  Parent AnalysisSession.
        dataset_id:  Source dataset.
        agent_name:  Name of the agent that completed (e.g. ``'schema'``).
        task_id:     ID of the completed TaskNode in the ExecutionPlan.
        success:     True when the agent produced a valid result.
        duration_ms: Wall-clock execution time of the agent.
        token_count: Total tokens consumed (input + output).
        cost_usd:    Estimated Bedrock cost for this invocation.
    """

    session_id: str = ""
    dataset_id: str = ""
    agent_name: str = ""
    task_id: str = ""
    success: bool = True
    duration_ms: int = 0
    token_count: int = 0
    cost_usd: float = 0.0

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update(
            {
                "session_id": self.session_id,
                "dataset_id": self.dataset_id,
                "agent_name": self.agent_name,
                "task_id": self.task_id,
                "success": self.success,
                "duration_ms": self.duration_ms,
                "token_count": self.token_count,
                "cost_usd": self.cost_usd,
            }
        )
        return base
