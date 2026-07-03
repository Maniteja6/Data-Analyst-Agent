"""BedrockStreamAdapter — real-time token streaming via ConverseStream.

Used exclusively by the WebSocket chat handler to deliver tokens to the
browser one-by-one as the model generates them, rather than waiting for
the full response before displaying anything.

ConverseStream is the streaming counterpart to Converse. It accepts the
same request body but returns an EventStream of ``contentBlockDelta`` events,
each containing a small chunk of text (typically 1-10 tokens).

The ``stream()`` async generator yields each text token as it arrives.
The WebSocket handler forwards each token as a ``chat:token`` Socket.IO event:

    async for token in adapter.stream(prompt="What is the trend?"):
        await sio.emit("chat:token", {"token": token, "message_id": mid}, to=sid)
    await sio.emit("chat:complete", {...}, to=sid)

Token aggregation:
    The caller is responsible for joining the tokens into the final response
    string. The ``chat:complete`` event should include the full concatenated text.

Thread safety:
    ``ConverseStream`` opens an HTTP/2 streaming response. The boto3 event
    stream consumer is synchronous, so we run it in a thread and bridge to
    asyncio via an ``asyncio.Queue``. This allows the caller to ``await`` each
    token without blocking the event loop.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

import structlog

from backend.infrastructure.llm.bedrock.bedrock_client import get_bedrock_runtime_client
from backend.infrastructure.llm.token_tracker import TokenTracker
from backend.config.bedrock_config import get_bedrock_config

logger = structlog.get_logger(__name__)

# Sentinel to signal end-of-stream from the reader thread
_STREAM_DONE = object()


class BedrockStreamAdapter:
    """Async streaming adapter wrapping Bedrock's ConverseStream API.

    Bridges the synchronous boto3 EventStream to an async generator via a
    background thread + asyncio Queue.
    """

    def __init__(self, token_tracker: TokenTracker | None = None) -> None:
        self._client        = get_bedrock_runtime_client()
        self._cfg           = get_bedrock_config()
        self._token_tracker = token_tracker or TokenTracker()

    async def stream(
        self,
        prompt: str,
        system: str | None = None,
        model_id: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncGenerator[str, None]:
        """Yield text tokens from a Bedrock ConverseStream response.

        Args:
            prompt:      User message content.
            system:      System prompt injected in the ``system`` parameter.
            model_id:    Bedrock model ID. Defaults to the primary model.
            max_tokens:  Override max output tokens.
            temperature: Override sampling temperature.

        Yields:
            Individual text tokens (strings) as they arrive from the model.
            The generator returns when the model finishes or the stream closes.

        Example::

            full_text = []
            async for token in adapter.stream("Summarise the revenue trends."):
                full_text.append(token)
                await websocket.send_text(token)
            complete_response = "".join(full_text)
        """
        model  = model_id or self._cfg.bedrock_model_id_primary
        body   = {
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {
                "maxTokens":   max_tokens   or self._cfg.bedrock_max_tokens,
                "temperature": temperature  if temperature is not None else self._cfg.bedrock_temperature,
                "topP":        self._cfg.bedrock_top_p,
            },
        }
        if system:
            body["system"] = [{"text": system}]

        # Queue bridges sync EventStream → async generator
        queue: asyncio.Queue[str | object] = asyncio.Queue(maxsize=512)
        loop  = asyncio.get_event_loop()

        # Token and metadata accumulators (populated in reader thread)
        meta: dict = {"input_tokens": 0, "output_tokens": 0, "stop_reason": "end_turn"}

        def _read_stream() -> None:
            """Synchronous reader — runs in a thread pool executor."""
            try:
                response = self._client.converse_stream(modelId=model, **body)
                for event in response.get("stream", []):
                    if "contentBlockDelta" in event:
                        delta = event["contentBlockDelta"].get("delta", {})
                        if "text" in delta:
                            loop.call_soon_threadsafe(queue.put_nowait, delta["text"])
                    elif "metadata" in event:
                        usage = event["metadata"].get("usage", {})
                        meta["input_tokens"]  = usage.get("inputTokens",  0)
                        meta["output_tokens"] = usage.get("outputTokens", 0)
                    elif "messageStop" in event:
                        meta["stop_reason"] = event["messageStop"].get("stopReason", "end_turn")
            except Exception as exc:
                logger.error("bedrock_stream_reader_error", error=str(exc), model=model)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, _STREAM_DONE)

        # Start the reader thread
        executor_future = loop.run_in_executor(None, _read_stream)

        # Yield tokens from the queue until the sentinel arrives
        try:
            while True:
                item = await queue.get()
                if item is _STREAM_DONE:
                    break
                yield item   # type: ignore[misc]
        finally:
            # Ensure the reader thread completes even if the caller cancels
            await executor_future

        # Record token usage after stream completes
        self._token_tracker.record(
            model=model,
            input_tokens=meta["input_tokens"],
            output_tokens=meta["output_tokens"],
        )
        logger.debug(
            "bedrock_stream_complete",
            model=model,
            input_tokens=meta["input_tokens"],
            output_tokens=meta["output_tokens"],
            stop_reason=meta["stop_reason"],
        )

    async def stream_to_string(
        self,
        prompt: str,
        system: str | None = None,
        model_id: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Stream tokens and join them into a single string.

        Convenience method for callers that want streaming token tracking
        but don't need to forward individual tokens to the client.
        """
        tokens = []
        async for token in self.stream(
            prompt=prompt,
            system=system,
            model_id=model_id,
            max_tokens=max_tokens,
        ):
            tokens.append(token)
        return "".join(tokens)
