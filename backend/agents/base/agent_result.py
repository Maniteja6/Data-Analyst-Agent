"""AgentResult — typed result envelope returned by every agent.

Stores the agent's output payload alongside execution metadata
(duration, token counts, cost estimate) so callers can make
cost-attribution decisions without parsing the payload.

Real-time integration:
    AgentResult is serialised to JSON and included in the
    ``analysis.complete`` Socket.IO event payload so the browser
    can display per-agent timing and cost breakdowns in the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Bedrock pricing (USD per 1M tokens) used for cost estimation
_PRICE_TABLE: dict[str, dict[str, float]] = {
    "anthropic.claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "anthropic.claude-haiku-4-5": {"input": 0.25, "output": 1.25},
    "amazon.titan-embed-text-v2:0": {"input": 0.02, "output": 0.00},
}
_DEFAULT_PRICE = {"input": 3.00, "output": 15.00}


@dataclass
class AgentResult:
    """Result envelope returned by BaseAgent.run().

    Attributes:
        agent_name:   Name of the agent that produced this result.
        success:      True when _execute() completed without exception.
        payload:      The value returned by _execute(). May be None on failure.
        error:        Error message string (None on success).
        duration_ms:  Wall-clock execution time in milliseconds.
        token_input:  Number of Bedrock input tokens consumed.
        token_output: Number of Bedrock output tokens generated.
        model_id:     Bedrock model ID used (for cost attribution).
        metadata:     Free-form dict for agent-specific supplemental data.
        created_at:   UTC timestamp of result creation.
    """

    agent_name: str
    success: bool
    payload: Any = None
    error: str | None = None
    duration_ms: int = 0
    token_input: int = 0
    token_output: int = 0
    model_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # ── Cost estimation ───────────────────────────────────────────────────

    @property
    def estimated_cost_usd(self) -> float:
        """Estimated USD cost based on token counts and model pricing."""
        prices = _PRICE_TABLE.get(self.model_id, _DEFAULT_PRICE)
        input_cost = (self.token_input / 1_000_000) * prices["input"]
        output_cost = (self.token_output / 1_000_000) * prices["output"]
        return round(input_cost + output_cost, 8)

    @property
    def total_tokens(self) -> int:
        return self.token_input + self.token_output

    # ── Convenience factories ─────────────────────────────────────────────

    @classmethod
    def success_result(
        cls,
        agent_name: str,
        payload: Any,  # noqa: ANN401
        duration_ms: int = 0,
        token_input: int = 0,
        token_output: int = 0,
        model_id: str = "",
    ) -> AgentResult:
        """Factory for successful results."""
        return cls(
            agent_name=agent_name,
            success=True,
            payload=payload,
            duration_ms=duration_ms,
            token_input=token_input,
            token_output=token_output,
            model_id=model_id,
        )

    @classmethod
    def failure_result(
        cls,
        agent_name: str,
        error: str,
        duration_ms: int = 0,
    ) -> AgentResult:
        """Factory for failed results."""
        return cls(
            agent_name=agent_name,
            success=False,
            error=error,
            duration_ms=duration_ms,
        )

    # ── Serialisation ─────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dict for Socket.IO events."""
        return {
            "agent_name": self.agent_name,
            "success": self.success,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "token_input": self.token_input,
            "token_output": self.token_output,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
            "model_id": self.model_id,
            "created_at": self.created_at.isoformat(),
        }

    def to_ws_event(self) -> dict[str, Any]:
        """Compact dict for the ``agent:complete`` Socket.IO event."""
        return {
            "agent": self.agent_name,
            "ok": self.success,
            "ms": self.duration_ms,
            "tokens": self.total_tokens,
            "cost_usd": self.estimated_cost_usd,
            "error": self.error,
        }
