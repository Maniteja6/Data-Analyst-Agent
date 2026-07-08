"""BedrockEmbeddingAdapter — raw boto3 wrapper for Titan Embeddings InvokeModel.

This is the lowest-level embedding adapter. Application code should prefer
``BedrockEmbeddingService`` in ``infrastructure/vector_store/`` which adds
batching, Redis caching, and a higher-level interface on top of this adapter.

``BedrockEmbeddingAdapter`` is kept separate from ``BedrockConverseAdapter``
because:
- Embeddings use ``InvokeModel`` (not ``Converse``)
- They produce a vector instead of text
- They are billed differently (no output tokens)
- They have different retry characteristics (rarely throttled vs Converse)

Usage (prefer ``BedrockEmbeddingService`` over direct use)::

    adapter = BedrockEmbeddingAdapter()
    vector = await adapter.embed("Total revenue column, Float64, currency")
    assert len(vector) == 1536
"""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import structlog
from backend.config.bedrock_config import get_bedrock_config
from backend.infrastructure.llm.bedrock.bedrock_client import get_bedrock_runtime_client
from backend.infrastructure.llm.bedrock.bedrock_retry_handler import with_bedrock_retry
from backend.infrastructure.llm.bedrock.model_configs.titan_embed import (
    DEFAULT_DIMENSIONS,
    build_request_body,
)
from backend.infrastructure.llm.token_tracker import TokenTracker

logger = structlog.get_logger(__name__)

# Dedicated thread pool for InvokeModel calls (separate from the S3 pool)
_EMBED_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="embed_worker")


class BedrockEmbeddingAdapter:
    """Raw async adapter for Amazon Titan Embeddings v2 via InvokeModel.

    All calls are dispatched to a thread pool because boto3 is synchronous.
    """

    def __init__(self, token_tracker: TokenTracker | None = None) -> None:
        self._client = get_bedrock_runtime_client()
        self._cfg = get_bedrock_config()
        self._token_tracker = token_tracker or TokenTracker()

    @with_bedrock_retry
    async def embed(
        self,
        text: str,
        dimensions: int = DEFAULT_DIMENSIONS,
    ) -> list[float]:
        """Embed a single text string and return the vector.

        Args:
            text:       Input text. Truncated to ``MAX_INPUT_CHARS`` if longer.
            dimensions: Output vector dimension (1536 / 512 / 256).

        Returns:
            Float list of length ``dimensions``.

        Raises:
            botocore.exceptions.ClientError: On Bedrock API errors (retried automatically).
        """
        body = json.dumps(build_request_body(text, dimensions))
        model = self._cfg.bedrock_embedding_model_id
        loop = asyncio.get_event_loop()

        def _invoke() -> Any:  # noqa: ANN401 — boto3 response dict, no type stubs
            return self._client.invoke_model(
                modelId=model,
                body=body,
                contentType="application/json",
                accept="application/json",
            )

        response = await loop.run_in_executor(_EMBED_EXECUTOR, _invoke)
        result = json.loads(response["body"].read())
        vector: list[float] = result["embedding"]

        # Titan Embed does not report token counts in the response;
        # approximate based on text length (1 token ≈ 4 chars)
        approx_tokens = max(1, len(text) // 4)
        self._token_tracker.record(
            model=model,
            input_tokens=approx_tokens,
            output_tokens=0,
        )

        logger.debug(
            "bedrock_embedding_complete",
            model=model,
            text_length=len(text),
            dimensions=dimensions,
            approx_tokens=approx_tokens,
        )
        return vector

    async def embed_batch_serial(
        self,
        texts: list[str],
        dimensions: int = DEFAULT_DIMENSIONS,
    ) -> list[list[float]]:
        """Embed a list of texts serially (slowest but avoids throttling).

        For concurrent embedding, use ``BedrockEmbeddingService.embed_batch()``.
        """
        return [await self.embed(t, dimensions) for t in texts]
