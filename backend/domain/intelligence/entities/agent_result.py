"""AgentResult entity — output record for one agent invocation."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from backend.shared.entity import Entity
from backend.domain.intelligence.value_objects.llm_response import LLMResponse


@dataclass
class AgentResult(Entity):
    """Persistent record of one agent's execution output.

    Stored in the ``agent_executions`` table for:
    - Debugging failed pipelines
    - Eval replay (re-run with the same input)
    - Audit trail (who queried what, when, at what cost)
    - Cache key storage (agent_input_hash → agent_result for repeated queries)

    Attributes:
        session_id:      Parent AnalysisSession (nullable for chat queries).
        conversation_id: Parent Conversation (nullable for batch analysis).
        agent_name:      Name of the agent that produced this result.
        task_id:         ID of the TaskNode in the ExecutionPlan.
        success:         True when the agent completed without raising.
        payload:         The agent's output data — schema varies by agent type.
        llm_response:    Raw LLM response VO (token counts, latency, model).
        input_hash:      SHA-256 of the serialised AgentInput (for cache lookup).
        output_hash:     SHA-256 of the serialised payload (for change detection).
        duration_ms:     Total wall-clock time including LLM latency.
        error:           Exception message if success=False.
        created_at:      UTC timestamp.
    """

    agent_name:      str
    session_id:      str | None         = None
    conversation_id: str | None         = None
    task_id:         str | None         = None
    success:         bool               = True
    payload:         Any                = None
    llm_response:    LLMResponse | None = None
    input_hash:      str | None         = None
    output_hash:     str | None         = None
    duration_ms:     int                = 0
    error:           str | None         = None
    created_at:      datetime | None    = None

    # ── Derived helpers ───────────────────────────────────────────────────

    @property
    def total_tokens(self) -> int:
        return self.llm_response.total_tokens if self.llm_response else 0

    @property
    def estimated_cost_usd(self) -> float:
        return self.llm_response.estimated_cost_usd if self.llm_response else 0.0

    @property
    def model_id(self) -> str | None:
        return self.llm_response.model_id if self.llm_response else None

    @property
    def was_truncated(self) -> bool:
        return self.llm_response.was_truncated if self.llm_response else False

    # ── Factory ───────────────────────────────────────────────────────────

    @classmethod
    def success_result(
        cls,
        agent_name: str,
        payload: Any,
        llm_response: LLMResponse | None = None,
        duration_ms: int = 0,
        session_id: str | None = None,
        conversation_id: str | None = None,
        task_id: str | None = None,
    ) -> "AgentResult":
        from backend.shared.utils.hash_utils import sha256_of_dict
        from backend.shared.utils.datetime_utils import utcnow
        import json
        try:
            output_hash = sha256_of_dict(payload) if isinstance(payload, dict) else None
        except Exception:
            output_hash = None
        return cls(
            agent_name=agent_name,
            session_id=session_id,
            conversation_id=conversation_id,
            task_id=task_id,
            success=True,
            payload=payload,
            llm_response=llm_response,
            output_hash=output_hash,
            duration_ms=duration_ms,
            created_at=utcnow(),
        )

    @classmethod
    def failure_result(
        cls,
        agent_name: str,
        error: str,
        duration_ms: int = 0,
        session_id: str | None = None,
        conversation_id: str | None = None,
    ) -> "AgentResult":
        from backend.shared.utils.datetime_utils import utcnow
        return cls(
            agent_name=agent_name,
            session_id=session_id,
            conversation_id=conversation_id,
            success=False,
            error=error,
            duration_ms=duration_ms,
            created_at=utcnow(),
        )

    def to_dict(self) -> dict:
        return {
            "id":             self.id,
            "agent_name":     self.agent_name,
            "session_id":     self.session_id,
            "conversation_id": self.conversation_id,
            "task_id":        self.task_id,
            "success":        self.success,
            "duration_ms":    self.duration_ms,
            "total_tokens":   self.total_tokens,
            "cost_usd":       self.estimated_cost_usd,
            "model_id":       self.model_id,
            "error":          self.error,
            "input_hash":     self.input_hash,
            "output_hash":    self.output_hash,
            "created_at":     self.created_at.isoformat() if self.created_at else None,
        }
