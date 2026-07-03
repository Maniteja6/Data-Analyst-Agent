"""BaseAgent — abstract base with retry, token tracking, cost tracking, and streaming support.

Designed for real-time applications:
- Async-first: every method is a coroutine
- Streaming: subclasses can override _execute_stream() to yield tokens
- Backpressure-safe: retry backoff uses asyncio.sleep (non-blocking)
- Observable: emits structured log events at every lifecycle step
- Cancellation-safe: CancelledError is never swallowed
"""
from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator

import structlog

from backend.agents.base.agent_context import AgentContext
from backend.agents.base.agent_result import AgentResult
from backend.shared.exceptions import AgentException

logger = structlog.get_logger(__name__)


class BaseAgent(ABC):
    """Abstract base for all DataPilot agents.

    Provides:
    - 3-attempt retry with jittered exponential backoff
    - Structured logging with correlation_id and session_id
    - Token and cost tracking via AgentResult
    - Optional streaming via _execute_stream()
    - OpenTelemetry span creation (no-op when OTel is not configured)
    """

    MAX_RETRIES:    int   = 3
    BASE_BACKOFF:   float = 1.5   # seconds; doubles per attempt
    MAX_BACKOFF:    float = 30.0  # cap

    def __init__(self, name: str) -> None:
        self.name    = name
        self._logger = structlog.get_logger(f"datapilot.agent.{name}")

    # ── Primary entry point ────────────────────────────────────────────────

    async def run(self, context: AgentContext, **kwargs: Any) -> AgentResult:
        """Run the agent with retry logic.

        Args:
            context: Shared mutable pipeline state.
            **kwargs: Agent-specific keyword arguments.

        Returns:
            AgentResult with success/failure state, payload, and metrics.

        Raises:
            AgentException: After all retry attempts are exhausted.
        """
        start      = time.monotonic()
        last_error: Exception | None = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                self._logger.info(
                    "agent_start",
                    attempt=attempt,
                    session_id=context.session_id,
                    correlation_id=context.correlation_id,
                )

                with self._otel_span(context):
                    result = await self._execute(context, **kwargs)

                duration_ms = int((time.monotonic() - start) * 1000)
                input_tokens, output_tokens = self._extract_tokens(result)

                self._logger.info(
                    "agent_complete",
                    duration_ms=duration_ms,
                    attempt=attempt,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )

                return AgentResult(
                    agent_name=self.name,
                    success=True,
                    payload=result,
                    duration_ms=duration_ms,
                    token_input=input_tokens,
                    token_output=output_tokens,
                )

            except AgentException:
                # Domain-level AgentExceptions are not retried
                raise

            except asyncio.CancelledError:
                # Always propagate cancellation
                raise

            except Exception as exc:
                last_error = exc
                self._logger.warning(
                    "agent_attempt_failed",
                    attempt=attempt,
                    max_retries=self.MAX_RETRIES,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )

                if attempt < self.MAX_RETRIES:
                    delay = min(
                        self.BASE_BACKOFF * (2 ** (attempt - 1)),
                        self.MAX_BACKOFF,
                    )
                    await asyncio.sleep(delay)

        duration_ms = int((time.monotonic() - start) * 1000)
        self._logger.error(
            "agent_all_attempts_failed",
            max_retries=self.MAX_RETRIES,
            last_error=str(last_error),
        )
        raise AgentException(
            self.name,
            f"All {self.MAX_RETRIES} attempts failed. Last error: {last_error}",
        )

    # ── Streaming entry point (for WebSocket real-time streaming) ──────────

    async def stream(
        self, context: AgentContext, **kwargs: Any
    ) -> AsyncGenerator[str, None]:
        """Stream agent output token by token (for WebSocket chat).

        Default implementation: runs _execute() and yields the full result
        as a single chunk. Agents that support true streaming override
        _execute_stream() instead.

        Usage::

            async for token in agent.stream(context, question="..."):
                await sio.emit("chat:token", {"token": token}, to=sid)
        """
        async for token in self._execute_stream(context, **kwargs):
            yield token

    async def _execute_stream(
        self, context: AgentContext, **kwargs: Any
    ) -> AsyncGenerator[str, None]:
        """Async generator yielding output tokens.

        Default: calls _execute() and yields the stringified result as one chunk.
        Override in agents that use BedrockStreamAdapter for true streaming.
        """
        result = await self._execute(context, **kwargs)
        yield str(result) if not isinstance(result, str) else result

    # ── Subclass contract ─────────────────────────────────────────────────

    @abstractmethod
    async def _execute(self, context: AgentContext, **kwargs: Any) -> Any:
        """Core agent logic. Must be implemented by every subclass.

        Args:
            context: Shared pipeline state. Subclasses read from and write
                     to AgentContext fields relevant to their role.
            **kwargs: Agent-specific arguments (e.g. question=, task=, query=).

        Returns:
            Any serialisable value that will be stored in AgentResult.payload.
        """
        ...

    # ── Internal helpers ──────────────────────────────────────────────────

    @staticmethod
    def _extract_tokens(result: Any) -> tuple[int, int]:
        """Extract token counts from agent result if present."""
        if isinstance(result, dict):
            return (
                int(result.get("input_tokens", 0)),
                int(result.get("output_tokens", 0)),
            )
        return 0, 0

    def _otel_span(self, context: AgentContext):
        """Return an OpenTelemetry span context manager (no-op if OTel absent)."""
        try:
            from opentelemetry import trace
            tracer = trace.get_tracer("datapilot.agents")
            return tracer.start_as_current_span(
                f"agent.{self.name}",
                attributes={
                    "agent.name":       self.name,
                    "session.id":       context.session_id,
                    "dataset.id":       context.dataset_id,
                    "correlation.id":   context.correlation_id,
                },
            )
        except Exception:
            return _NoOpSpan()


class _NoOpSpan:
    """Fallback context manager when OpenTelemetry is not available."""
    def __enter__(self):  return self
    def __exit__(self, *_): pass
