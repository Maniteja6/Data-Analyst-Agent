"""AgentInput value object — immutable input envelope passed to every agent."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.shared.value_object import ValueObject


@dataclass(frozen=True)
class AgentInput(ValueObject):
    """Immutable, typed input envelope for a single agent invocation.

    Rather than passing raw dicts between agents, the orchestrator wraps
    inputs in this VO. This makes agent contracts explicit and auditable —
    the full input can be serialised to JSON and stored in the
    ``agent_executions`` table for debugging and eval replay.

    Attributes:
        session_id:     Parent AnalysisSession UUID.
        dataset_id:     Source dataset UUID.
        correlation_id: Request-scoped tracing ID propagated from the upload.
        storage_key:    S3/MinIO object key for the dataset file.
        task_id:        ID of the TaskNode in the ExecutionPlan.
        agent_name:     Name of the target agent (matches agent_registry key).
        payload:        Agent-specific input data. Kept as a frozenset of items
                        to maintain hashability; use ``payload_dict`` to get a dict.
        metadata:       Optional key-value pairs for agent-specific config
                        (e.g. ``{'max_rows': 1000, 'target_col': 'revenue'}``).
    """

    session_id:     str
    dataset_id:     str
    correlation_id: str
    storage_key:    str
    task_id:        str
    agent_name:     str
    # Frozen dicts aren't hashable, so we store as a tuple of pairs
    _payload_items: tuple = field(default_factory=tuple)
    _metadata_items: tuple = field(default_factory=tuple)

    def _validate(self) -> None:
        if not self.agent_name:
            raise ValueError("agent_name must not be empty")
        if not self.session_id:
            raise ValueError("session_id must not be empty")

    # ── Payload access ────────────────────────────────────────────────────

    @property
    def payload(self) -> dict[str, Any]:
        """Return the payload as a plain dict."""
        return dict(self._payload_items)

    @property
    def metadata(self) -> dict[str, Any]:
        """Return the metadata as a plain dict."""
        return dict(self._metadata_items)

    # ── Factory ───────────────────────────────────────────────────────────

    @classmethod
    def create(
        cls,
        session_id: str,
        dataset_id: str,
        correlation_id: str,
        storage_key: str,
        task_id: str,
        agent_name: str,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "AgentInput":
        """Create an AgentInput, converting dicts to frozen tuple pairs."""
        return cls(
            session_id=session_id,
            dataset_id=dataset_id,
            correlation_id=correlation_id,
            storage_key=storage_key,
            task_id=task_id,
            agent_name=agent_name,
            _payload_items=tuple(sorted((payload or {}).items())),
            _metadata_items=tuple(sorted((metadata or {}).items())),
        )

    def with_payload(self, **kwargs: Any) -> "AgentInput":
        """Return a new AgentInput with additional payload fields merged in."""
        merged = {**self.payload, **kwargs}
        return AgentInput.create(
            session_id=self.session_id,
            dataset_id=self.dataset_id,
            correlation_id=self.correlation_id,
            storage_key=self.storage_key,
            task_id=self.task_id,
            agent_name=self.agent_name,
            payload=merged,
            metadata=self.metadata,
        )

    def to_dict(self) -> dict:
        return {
            "session_id":     self.session_id,
            "dataset_id":     self.dataset_id,
            "correlation_id": self.correlation_id,
            "storage_key":    self.storage_key,
            "task_id":        self.task_id,
            "agent_name":     self.agent_name,
            "payload":        self.payload,
            "metadata":       self.metadata,
        }
