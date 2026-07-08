"""BedrockEmbeddingService — text embeddings via Amazon Titan Embed v2.

Used exclusively by the RAG pipeline to:
1. **Index** — embed schema chunks and profile summaries at profiling time,
   upserted into Qdrant under ``collection_name`` with ``dataset_id`` as payload.
2. **Query** — embed user questions (optionally via HyDE expansion) at chat
   time and retrieve the top-K most similar chunks from Qdrant.

Titan Embed Text v2 produces 1536-dimensional L2-normalised vectors by default.
The dimension can be reduced to 512 or 256 via the ``dimensions`` parameter to
cut Qdrant storage cost at the price of some retrieval quality.

Embedding latency is ~120 ms per call (warm) — acceptable for RAG retrieval
but too slow for per-token streaming. Embeddings are cached in Redis for 24h
to avoid re-embedding the same chunk text on re-analysis runs.

Usage::

    from backend.infrastructure.vector_store.bedrock_embedding_service import (
        BedrockEmbeddingService
    )

    embed = BedrockEmbeddingService()
    vector = await embed.embed("Total revenue column, Float64, 0.3% null rate")
    vectors = await embed.embed_batch(["col_a description…", "col_b description…"])
"""

from __future__ import annotations

import asyncio
import json
from functools import lru_cache
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from backend.infrastructure.cache.redis_cache_adapter import RedisCacheAdapter

logger = structlog.get_logger(__name__)


class BedrockEmbeddingService:
    """Async wrapper around the Bedrock Titan Embed Text v2 API.

    Delegates actual boto3 calls to a thread pool executor so the caller
    never blocks the event loop. Includes optional Redis caching to avoid
    re-embedding identical texts.
    """

    _MAX_INPUT_TOKENS = 8192  # Titan Embed v2 limit
    _MAX_CHARS = 32_000  # ~8k tokens at ~4 chars/token; safe truncation point

    def __init__(
        self,
        dimensions: int = 1536,
        normalize: bool = True,
        cache: RedisCacheAdapter | None = None,
    ) -> None:
        """
        Args:
            dimensions: Output vector dimension (1536 / 512 / 256).
            normalize:  Return L2-normalised vectors (recommended for cosine similarity).
            cache:      Optional ``RedisCacheAdapter`` instance for embedding caching.
                        When None, caching is disabled.
        """
        self._dimensions = dimensions
        self._normalize = normalize
        self._cache = cache
        self._client = None  # lazily initialised

    # ── Client factory ────────────────────────────────────────────────────

    def _get_client(self) -> Any:  # noqa: ANN401 — boto3 client has no static type without stubs
        if self._client is None:
            from backend.infrastructure.llm.bedrock.bedrock_client import get_bedrock_runtime_client

            self._client = get_bedrock_runtime_client()
        return self._client

    # ── Cache helpers ─────────────────────────────────────────────────────

    def _cache_key(self, text: str) -> str:
        from backend.shared.utils.hash_utils import sha256_of_string

        return f"embed:{self._dimensions}:{sha256_of_string(text)}"

    async def _get_cached(self, text: str) -> list[float] | None:
        if self._cache is None:
            return None
        raw = await self._cache.get(self._cache_key(text))
        return json.loads(raw) if raw else None

    async def _set_cached(self, text: str, vector: list[float]) -> None:
        if self._cache is not None:
            await self._cache.set(
                self._cache_key(text),
                json.dumps(vector),
                ttl=86400,  # 24-hour cache
            )

    # ── Embedding ─────────────────────────────────────────────────────────

    async def embed(self, text: str) -> list[float]:
        """Generate a dense vector for a single text string.

        Args:
            text: Input text. Truncated to ``_MAX_CHARS`` if longer.

        Returns:
            Float list of length ``self._dimensions``.

        Raises:
            RuntimeError: If the Bedrock call fails and no cached vector exists.
        """
        # Truncate to safe char limit (Titan Embed truncates silently beyond token limit)
        text = text[: self._MAX_CHARS]

        # Cache hit
        cached = await self._get_cached(text)
        if cached is not None:
            return cached

        # Bedrock call (blocking boto3 → thread pool)
        from backend.config.bedrock_config import get_bedrock_config

        cfg = get_bedrock_config()
        client = self._get_client()

        body = json.dumps(
            {
                "inputText": text,
                "dimensions": self._dimensions,
                "normalize": self._normalize,
            }
        )

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.invoke_model(
                modelId=cfg.bedrock_embedding_model_id,
                body=body,
                contentType="application/json",
                accept="application/json",
            ),
        )

        result = json.loads(response["body"].read())
        vector: list[float] = result["embedding"]

        logger.debug(
            "embedding_generated",
            text_length=len(text),
            dimensions=self._dimensions,
        )

        # Cache for future requests
        await self._set_cached(text, vector)
        return vector

    async def embed_batch(
        self,
        texts: list[str],
        concurrency: int = 4,
    ) -> list[list[float]]:
        """Embed a list of texts with controlled concurrency.

        Titan Embed v2 has no native batch endpoint, so calls are issued
        concurrently (bounded by ``concurrency``) rather than serially.

        Args:
            texts:       List of input strings.
            concurrency: Maximum parallel Bedrock calls (default: 4).
                         Keep below 10 to stay within the service throttle limit.

        Returns:
            List of float vectors in the same order as ``texts``.
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def _embed_one(text: str) -> list[float]:
            async with semaphore:
                return await self.embed(text)

        vectors = await asyncio.gather(*[_embed_one(t) for t in texts])
        logger.info("embedding_batch_complete", count=len(texts), dimensions=self._dimensions)
        return list(vectors)

    async def similarity(self, vec_a: list[float], vec_b: list[float]) -> float:
        """Compute cosine similarity between two vectors.

        Returns a value in [0, 1] when vectors are L2-normalised (``normalize=True``).
        Useful for testing retrieval quality in evals.
        """
        import math

        dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
        mag_a = math.sqrt(sum(a * a for a in vec_a))
        mag_b = math.sqrt(sum(b * b for b in vec_b))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return round(dot / (mag_a * mag_b), 6)


@lru_cache(maxsize=1)
def get_embedding_service() -> BedrockEmbeddingService:
    """Return the cached embedding service singleton."""
    return BedrockEmbeddingService()
