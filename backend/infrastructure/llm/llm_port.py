"""ILLMService — abstract LLM port for the application layer.

The application layer (use cases, event handlers) depends on this abstract
interface, not on ``BedrockConverseAdapter`` directly. This allows:

1. **Testability** — swap in a ``MockLLMService`` without boto3 or AWS creds.
2. **Vendor portability** — replace Bedrock with OpenAI or a local Ollama
   server by implementing this interface without touching application code.
3. **Feature flag integration** — route calls to a cheaper model for non-critical
   tasks by wrapping the real adapter in a ``CostOptimisedLLMService``.

Implementations
---------------
``BedrockLLMService``  — production adapter in this module (wraps BedrockConverseAdapter)
``MockLLMService``     — test double that returns configurable canned responses
``NullLLMService``     — no-op that returns empty strings (disables AI for cost-saving)

Registration
------------
The concrete implementation is injected via ``api/dependencies.py``:

    def get_llm_service() -> ILLMService:
        if settings.app_env == "test":
            return MockLLMService()
        return BedrockLLMService()
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any


class ILLMService(ABC):
    """Abstract LLM service port.

    All methods are async to support both synchronous (mock) and network-bound
    (Bedrock) implementations without changing the call site.
    """

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        model_id: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        response_format: type | None = None,
    ) -> str:
        """Send a single user turn and return the assistant response text."""

    @abstractmethod
    async def converse(
        self,
        messages: list[dict],
        system: str | None = None,
        model_id: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Multi-turn conversation using the full message history."""

    @abstractmethod
    async def stream(
        self,
        prompt: str,
        system: str | None = None,
        model_id: str | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream response tokens one-by-one."""
        raise NotImplementedError
        yield  # pragma: no cover — makes this an async generator function for typing purposes

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Generate a dense embedding vector for a text string."""


# ---------------------------------------------------------------------------
# Production implementation
# ---------------------------------------------------------------------------


class BedrockLLMService(ILLMService):
    """Production ILLMService backed by AWS Bedrock.

    Wraps ``BedrockConverseAdapter``, ``BedrockStreamAdapter``, and
    ``BedrockEmbeddingAdapter`` behind a single cohesive interface.
    """

    def __init__(self) -> None:
        from backend.infrastructure.llm.bedrock.bedrock_converse_adapter import (
            BedrockConverseAdapter,
        )
        from backend.infrastructure.llm.bedrock.bedrock_stream_adapter import BedrockStreamAdapter
        from backend.infrastructure.vector_store.bedrock_embedding_service import (
            BedrockEmbeddingService,
        )

        self._converse = BedrockConverseAdapter()
        self._stream = BedrockStreamAdapter()
        self._embedding = BedrockEmbeddingService()

    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        model_id: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        response_format: type | None = None,
    ) -> str:
        return await self._converse.complete(
            prompt=prompt,
            system=system,
            model_id=model_id,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format=response_format,
        )

    async def converse(
        self,
        messages: list[dict],
        system: str | None = None,
        model_id: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        return await self._converse.converse_multi_turn(
            messages=messages,
            system=system,
            model_id=model_id,
            max_tokens=max_tokens,
        )

    async def stream(
        self,
        prompt: str,
        system: str | None = None,
        model_id: str | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        async for token in self._stream.stream(
            prompt=prompt,
            system=system,
            model_id=model_id,
            max_tokens=max_tokens,
        ):
            yield token

    async def embed(self, text: str) -> list[float]:
        return await self._embedding.embed(text)


# ---------------------------------------------------------------------------
# Test double
# ---------------------------------------------------------------------------


class MockLLMService(ILLMService):
    """Configurable mock LLM service for unit and integration tests.

    Returns canned responses defined via ``set_response()`` or a default
    JSON-safe string when no response is configured for the prompt.

    Records all calls in ``calls`` for assertion in tests.

    Usage::

        mock = MockLLMService()
        mock.set_response("List insights", '{"insights": []}')
        result = await mock.complete("List insights")
        assert result == '{"insights": []}'
        assert mock.calls[0]["prompt"] == "List insights"
    """

    def __init__(self, default_response: str = '{"result": "mock"}') -> None:
        self._default = default_response
        self._responses: dict[str, str] = {}
        self.calls: list[dict[str, Any]] = []

    def set_response(self, prompt_contains: str, response: str) -> None:
        """Register a canned response for prompts containing ``prompt_contains``."""
        self._responses[prompt_contains] = response

    def _match(self, prompt: str) -> str:
        for key, val in self._responses.items():
            if key in prompt:
                return val
        return self._default

    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        model_id: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        response_format: type | None = None,
    ) -> str:
        self.calls.append({"method": "complete", "prompt": prompt, "model_id": model_id})
        return self._match(prompt)

    async def converse(
        self,
        messages: list[dict],
        system: str | None = None,
        model_id: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        last_user = next(
            (m["content"][0]["text"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        self.calls.append({"method": "converse", "last_user_message": last_user})
        return self._match(last_user)

    async def stream(
        self,
        prompt: str,
        system: str | None = None,
        model_id: str | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        response = self._match(prompt)
        self.calls.append({"method": "stream", "prompt": prompt})
        for word in response.split():
            yield word + " "

    async def embed(self, text: str) -> list[float]:
        self.calls.append({"method": "embed", "text": text[:50]})
        # Return a deterministic zero vector for testing
        return [0.0] * 1536

    def reset(self) -> None:
        """Clear all recorded calls and configured responses."""
        self.calls.clear()
        self._responses.clear()


# ---------------------------------------------------------------------------
# No-op implementation
# ---------------------------------------------------------------------------


class NullLLMService(ILLMService):
    """LLM service that always returns empty strings.

    Use when AI features should be disabled entirely (cost-saving mode,
    offline testing, or when the ``FEATURE_RAG`` / ``FEATURE_ML_AGENT``
    flags are all disabled).
    """

    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        model_id: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        response_format: type | None = None,
    ) -> str:
        return ""

    async def converse(
        self,
        messages: list[dict],
        system: str | None = None,
        model_id: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        return ""

    async def stream(
        self,
        prompt: str,
        system: str | None = None,
        model_id: str | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        return
        yield  # make it a generator

    async def embed(self, text: str) -> list[float]:
        return [0.0] * 1536
