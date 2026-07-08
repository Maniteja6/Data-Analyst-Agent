"""TokenTracker — thread-safe in-process LLM token usage accumulator.

Records the number of input and output tokens consumed across all Bedrock
API calls made during the lifetime of a worker process. Broken down by
model ID.

Used by:
- ``BedrockConverseAdapter``  — records after each Converse response
- ``BedrockStreamAdapter``    — records after each ConverseStream completes
- ``BedrockEmbeddingAdapter`` — records approximate token count per embed call

The tracker is intentionally simple:
- Thread-safe (``threading.Lock`` protects the totals dict)
- In-process only (no Redis, no external state)
- Accumulates until ``reset()`` is called (typically between test cases)

For session-level cost tracking, use ``BedrockCostTracker`` instead.
For aggregated metrics emitted to Prometheus, see ``prometheus_metrics.llm_tokens_total``.

Usage::

    tracker = TokenTracker()
    tracker.record("anthropic.claude-sonnet-4-5", input_tokens=512, output_tokens=128)
    tracker.record("anthropic.claude-haiku-4-5",  input_tokens=256, output_tokens=64)

    summary = tracker.summary()
    # {
    #   "anthropic.claude-sonnet-4-5": {"input": 512, "output": 128, "total": 640},
    #   "anthropic.claude-haiku-4-5":  {"input": 256, "output":  64, "total": 320},
    # }

    tracker.total_input_tokens   # 768
    tracker.total_output_tokens  # 192
    tracker.grand_total_tokens   # 960
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ModelUsage:
    """Per-model token usage accumulator."""

    input_tokens: int = 0
    output_tokens: int = 0
    call_count: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, int]:
        return {
            "input": self.input_tokens,
            "output": self.output_tokens,
            "total": self.total_tokens,
            "call_count": self.call_count,
        }


class TokenTracker:
    """Thread-safe in-process token usage accumulator.

    One instance is typically shared across all Bedrock adapters in one
    worker process. When injected into adapters via the constructor, separate
    instances can be used per agent execution for per-agent breakdowns.
    """

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._usage: dict[str, ModelUsage] = {}

    # ── Recording ─────────────────────────────────────────────────────────

    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Thread-safely accumulate token counts for a model.

        Args:
            model:         Bedrock model ID string.
            input_tokens:  Number of prompt tokens consumed.
            output_tokens: Number of completion tokens generated.
        """
        with self._lock:
            usage = self._usage.setdefault(model, ModelUsage())
            usage.input_tokens += input_tokens
            usage.output_tokens += output_tokens
            usage.call_count += 1

    # ── Aggregated views ──────────────────────────────────────────────────

    @property
    def total_input_tokens(self) -> int:
        """Sum of input tokens across all models."""
        with self._lock:
            return sum(u.input_tokens for u in self._usage.values())

    @property
    def total_output_tokens(self) -> int:
        """Sum of output tokens across all models."""
        with self._lock:
            return sum(u.output_tokens for u in self._usage.values())

    @property
    def grand_total_tokens(self) -> int:
        """Total tokens (input + output) across all models."""
        return self.total_input_tokens + self.total_output_tokens

    @property
    def total_call_count(self) -> int:
        """Total number of Bedrock API calls recorded."""
        with self._lock:
            return sum(u.call_count for u in self._usage.values())

    @property
    def models_used(self) -> list[str]:
        """List of model IDs that have been called at least once."""
        with self._lock:
            return list(self._usage.keys())

    # ── Serialisation ─────────────────────────────────────────────────────

    def summary(self) -> dict[str, dict[str, int]]:
        """Return a snapshot of token usage per model.

        Returns:
            Dict mapping model ID → ``{input, output, total, call_count}``.

        Thread-safe — returns a deep copy so the caller can inspect it
        without holding the lock.
        """
        with self._lock:
            return {model: usage.to_dict() for model, usage in self._usage.items()}

    def grand_summary(self) -> dict[str, Any]:
        """Return aggregated totals across all models."""
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "grand_total_tokens": self.grand_total_tokens,
            "total_call_count": self.total_call_count,
            "models_used": self.models_used,
            "per_model": self.summary(),
        }

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Clear all accumulated totals.

        Call between test cases or between pipeline runs to prevent
        cross-run token count leakage.
        """
        with self._lock:
            self._usage.clear()

    def snapshot_and_reset(self) -> dict[str, dict[str, int]]:
        """Return the current summary and atomically reset all counters.

        Useful at the end of a pipeline run to capture the final totals
        before the next run starts:

            totals = tracker.snapshot_and_reset()
            await audit_logger.log_agent_execution(token_count=sum(...))
        """
        with self._lock:
            snap = {model: usage.to_dict() for model, usage in self._usage.items()}
            self._usage.clear()
        return snap

    # ── Prometheus integration helper ─────────────────────────────────────

    def emit_prometheus_metrics(self, agent_name: str = "") -> None:
        """Emit current token counts to Prometheus.

        Safe to call on every agent completion — will no-op if the
        prometheus_metrics module is not importable.
        """
        try:
            from backend.infrastructure.observability.prometheus_metrics import llm_tokens_total

            with self._lock:
                for model, usage in self._usage.items():
                    llm_tokens_total.labels(
                        agent_name=agent_name,
                        model=model,
                        token_type="input",
                    ).inc(usage.input_tokens)
                    llm_tokens_total.labels(
                        agent_name=agent_name,
                        model=model,
                        token_type="output",
                    ).inc(usage.output_tokens)
        except Exception as exc:
            logger.debug("token_usage_metrics_emit_failed", error=str(exc))
