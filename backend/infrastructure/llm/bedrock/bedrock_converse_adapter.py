"""BedrockConverseAdapter — primary text completion adapter using the Converse API.

The Bedrock Converse API is the preferred interface over ``InvokeModel`` because:
- Same API structure across all models (Claude, Titan, Llama, Mistral, etc.)
- Native multi-turn message history support
- Separate ``system`` parameter (no need to inject system prompts into user turns)
- Consistent token usage reporting
- Streaming via ``ConverseStream`` with the same request structure

All agent ``_execute()`` methods call ``BedrockConverseAdapter.complete()``
for single-turn prompts and ``converse_multi_turn()`` for multi-turn chat
sessions (passing the conversation history).

Usage::

    adapter = BedrockConverseAdapter()

    # Single-turn with JSON output
    text = await adapter.complete(
        prompt="List the top 5 insights in JSON format.",
        system="You are a data analyst. Return only valid JSON.",
        response_format=dict,   # hints JSON-only output
    )

    # Multi-turn conversation
    messages = [
        {"role": "user",      "content": [{"text": "What is the average revenue?"}]},
        {"role": "assistant", "content": [{"text": "The average is $42,300."}]},
        {"role": "user",      "content": [{"text": "How does that compare to Q3?"}]},
    ]
    reply = await adapter.converse_multi_turn(messages, system="Dataset context…")
"""
from __future__ import annotations

import time

import structlog

from backend.infrastructure.llm.bedrock.bedrock_client import get_bedrock_runtime_client
from backend.infrastructure.llm.bedrock.bedrock_retry_handler import with_bedrock_retry
from backend.infrastructure.llm.token_tracker import TokenTracker
from backend.domain.intelligence.value_objects.llm_response import LLMResponse, ResponseType
from backend.config.bedrock_config import get_bedrock_config

logger = structlog.get_logger(__name__)

_JSON_SYSTEM_SUFFIX = (
    "\n\nIMPORTANT: Respond ONLY with valid JSON. "
    "No markdown fences, no explanation, no preamble."
)
_SQL_SYSTEM_SUFFIX = (
    "\n\nRespond ONLY with the SQL query. "
    "No markdown fences, no explanation."
)


class BedrockConverseAdapter:
    """Async wrapper around the Bedrock Converse API.

    All methods return ``LLMResponse`` value objects so callers have access
    to the raw text, token counts, latency, and stop reason without needing
    to inspect the boto3 response dict directly.
    """

    def __init__(
        self,
        token_tracker: TokenTracker | None = None,
        cost_tracker=None,
    ) -> None:
        self._client       = get_bedrock_runtime_client()
        self._cfg          = get_bedrock_config()
        self._token_tracker = token_tracker or TokenTracker()
        self._cost_tracker  = cost_tracker

    # ── Single-turn completion ────────────────────────────────────────────

    @with_bedrock_retry
    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        model_id: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        response_format: type | None = None,
    ) -> str:
        """Send one user turn and return the assistant text.

        Args:
            prompt:          User message content.
            system:          System prompt injected via the Converse ``system`` param.
            model_id:        Bedrock model ID. Defaults to the primary model (Sonnet).
            max_tokens:      Override ``BedrockConfig.bedrock_max_tokens``.
            temperature:     Override ``BedrockConfig.bedrock_temperature``.
            response_format: When ``dict`` or ``list``, appends a JSON-only instruction
                             to the system prompt and returns the raw JSON string.

        Returns:
            Stripped text content of the assistant response.
        """
        llm_resp = await self._complete_llm_response(
            prompt=prompt,
            system=system,
            model_id=model_id,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format=response_format,
        )
        return llm_resp.content

    async def complete_with_metadata(
        self,
        prompt: str,
        system: str | None = None,
        model_id: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        response_format: type | None = None,
    ) -> LLMResponse:
        """Like ``complete()`` but returns the full ``LLMResponse`` VO.

        Use when the caller needs token counts, latency, or stop reason
        (e.g. ``BedrockCostTracker``, ``AgentResult`` entity).
        """
        return await self._complete_llm_response(
            prompt=prompt,
            system=system,
            model_id=model_id,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format=response_format,
        )

    @with_bedrock_retry
    async def _complete_llm_response(
        self,
        prompt: str,
        system: str | None,
        model_id: str | None,
        max_tokens: int | None,
        temperature: float | None,
        response_format: type | None,
    ) -> LLMResponse:
        """Internal implementation that returns a full LLMResponse VO."""
        model  = model_id or self._cfg.bedrock_model_id_primary
        system = self._build_system(system, response_format)

        body = self._build_converse_body(
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if system:
            body["system"] = [{"text": system}]

        start    = time.monotonic()
        response = self._client.converse(modelId=model, **body)
        latency  = int((time.monotonic() - start) * 1000)

        return self._parse_response(response, model, latency, response_format)

    # ── Multi-turn completion ─────────────────────────────────────────────

    @with_bedrock_retry
    async def converse_multi_turn(
        self,
        messages: list[dict],
        system: str | None = None,
        model_id: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Multi-turn conversation — pass the full message history.

        The caller is responsible for maintaining the message list in the
        ``[{role, content}, …]`` format required by the Converse API.
        Messages alternate user/assistant; the first must be from the user.

        Args:
            messages:   Full conversation history in Bedrock Converse format.
            system:     System prompt (injected separately from messages).
            model_id:   Bedrock model ID. Defaults to the primary model.
            max_tokens: Override max output tokens.

        Returns:
            Text content of the latest assistant response.
        """
        model = model_id or self._cfg.bedrock_model_id_primary
        body  = self._build_converse_body(messages=messages, max_tokens=max_tokens)
        if system:
            body["system"] = [{"text": system}]

        start    = time.monotonic()
        response = self._client.converse(modelId=model, **body)
        latency  = int((time.monotonic() - start) * 1000)

        llm_resp = self._parse_response(response, model, latency, response_format=None)
        return llm_resp.content

    # ── Private helpers ───────────────────────────────────────────────────

    def _build_converse_body(
        self,
        messages: list[dict],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict:
        """Build the common Converse API request body dict."""
        return {
            "messages": messages,
            "inferenceConfig": {
                "maxTokens":   max_tokens   or self._cfg.bedrock_max_tokens,
                "temperature": temperature  if temperature is not None else self._cfg.bedrock_temperature,
                "topP":        self._cfg.bedrock_top_p,
            },
        }

    @staticmethod
    def _build_system(
        system: str | None,
        response_format: type | None,
    ) -> str | None:
        """Append format instructions to the system prompt when needed."""
        if response_format in (dict, list):
            return (system or "") + _JSON_SYSTEM_SUFFIX
        return system

    def _parse_response(
        self,
        response: dict,
        model: str,
        latency_ms: int,
        response_format: type | None,
    ) -> LLMResponse:
        """Extract content, tokens, and stop reason from a Converse API response."""
        content     = response["output"]["message"]["content"][0]["text"].strip()
        usage       = response.get("usage", {})
        stop_reason = response.get("stopReason", "end_turn")

        input_tokens  = usage.get("inputTokens",  0)
        output_tokens = usage.get("outputTokens", 0)

        # Record in token tracker and optional cost tracker
        self._token_tracker.record(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        if self._cost_tracker:
            self._cost_tracker.record_invocation(model, input_tokens, output_tokens)

        rtype = ResponseType.JSON if response_format in (dict, list) else ResponseType.TEXT

        logger.debug(
            "bedrock_converse_complete",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            stop_reason=stop_reason,
        )

        return LLMResponse(
            content=content,
            model_id=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            stop_reason=stop_reason,
            response_type=rtype,
            latency_ms=latency_ms,
        )
