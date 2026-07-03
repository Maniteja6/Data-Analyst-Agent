"""LLMResponseCache — Redis-backed cache for repeated identical LLM prompts.

Avoids re-calling Bedrock for identical (model_id, prompt) pairs by storing
the response text in Redis under a SHA-256 key. Saves both latency (~1-3s
round-trip) and cost ($3/1M tokens for Sonnet).

When to use this cache:
- Schema inference on repeated uploads of the same file (same schema → same
  classification prompt → same semantic types)
- Repeated chat queries about the same dataset within the TTL window
- Agent re-runs during pipeline retries when the input hasn't changed

When NOT to use:
- Prompts that embed timestamps, random seeds, or user-specific context
  (different context → different prompt → different cache key)
- Streaming responses (the cache returns a complete string, not a stream)

Cache key construction:
    SHA-256(model_id + ":" + prompt_text)

    The model_id is included so that routing the same prompt to Haiku vs
    Sonnet produces separate cache entries (they may give different outputs).

    Temperature is NOT part of the key because most agents use a fixed
    temperature (0.1). If your use case varies temperature per call, pass
    the temperature as part of the prompt or disable caching for those calls.

TTL: 24 hours (configurable via ``Settings.redis_ttl_seconds``).

Usage::

    cache = LLMResponseCache()

    # Check before calling Bedrock
    cached = await cache.get(model_id, prompt)
    if cached:
        return cached   # instant, free

    # Call Bedrock
    response = await adapter.complete(prompt, model_id=model_id)

    # Store for next time
    await cache.set(model_id, prompt, response)
    return response
"""
from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


class LLMResponseCache:
    """Redis-backed LLM response cache.

    Accepts any async cache adapter that implements ``get(key)`` and
    ``set(key, value, ttl)``, making it compatible with both
    ``RedisCacheAdapter`` (production) and ``InMemoryCacheAdapter`` (tests).
    """

    _KEY_PREFIX = "llm_cache:"

    def __init__(
        self,
        cache_adapter=None,
        ttl: int | None = None,
        enabled: bool = True,
    ) -> None:
        """
        Args:
            cache_adapter: Async cache adapter instance. When None, the Redis
                           singleton is used.
            ttl:           Cache TTL in seconds. Defaults to ``Settings.redis_ttl_seconds``.
            enabled:       Set False to disable caching (e.g. for debugging).
        """
        self._cache   = cache_adapter
        self._ttl     = ttl
        self._enabled = enabled
        self._hits    = 0   # diagnostic counter
        self._misses  = 0

    # ── Cache operations ──────────────────────────────────────────────────

    async def get(self, model_id: str, prompt: str) -> str | None:
        """Return a cached response, or None on cache miss.

        Args:
            model_id: Bedrock model ID (part of the cache key).
            prompt:   Full prompt text.

        Returns:
            Cached response text, or None if not found / caching disabled.
        """
        if not self._enabled:
            return None

        key = self._build_key(model_id, prompt)
        try:
            adapter  = self._get_adapter()
            response = await adapter.get(key)
            if response is not None:
                self._hits += 1
                logger.debug(
                    "llm_cache_hit",
                    model=model_id,
                    key=key[:16],
                    hits=self._hits,
                )
                return response
            self._misses += 1
            return None
        except Exception as exc:
            logger.debug("llm_cache_get_failed", error=str(exc))
            return None

    async def set(self, model_id: str, prompt: str, response: str) -> None:
        """Store a response in the cache.

        Args:
            model_id: Bedrock model ID.
            prompt:   Full prompt text (used to compute the cache key).
            response: Complete response text to cache.
        """
        if not self._enabled or not response:
            return

        key = self._build_key(model_id, prompt)
        try:
            adapter = self._get_adapter()
            ttl     = self._ttl or self._default_ttl()
            await adapter.set(key, response, ttl=ttl)
            logger.debug(
                "llm_cache_set",
                model=model_id,
                key=key[:16],
                ttl=ttl,
                response_length=len(response),
            )
        except Exception as exc:
            logger.debug("llm_cache_set_failed", error=str(exc))

    async def invalidate(self, model_id: str, prompt: str) -> None:
        """Remove a specific entry from the cache."""
        if not self._enabled:
            return
        key = self._build_key(model_id, prompt)
        try:
            await self._get_adapter().delete(key)
        except Exception as exc:
            logger.debug("llm_cache_invalidate_failed", error=str(exc))

    async def invalidate_all(self) -> int:
        """Delete all LLM cache entries. Returns the count deleted."""
        try:
            return await self._get_adapter().delete_pattern(f"{self._KEY_PREFIX}*")
        except Exception as exc:
            logger.warning("llm_cache_flush_failed", error=str(exc))
            return 0

    # ── Diagnostics ───────────────────────────────────────────────────────

    @property
    def hit_count(self) -> int:
        return self._hits

    @property
    def miss_count(self) -> int:
        return self._misses

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return round(self._hits / total, 4) if total > 0 else 0.0

    def reset_counters(self) -> None:
        """Reset hit/miss counters — useful between test cases."""
        self._hits   = 0
        self._misses = 0

    # ── Private helpers ───────────────────────────────────────────────────

    def _build_key(self, model_id: str, prompt: str) -> str:
        """Construct the Redis key for a (model_id, prompt) pair."""
        from backend.shared.utils.hash_utils import llm_cache_key
        return self._KEY_PREFIX + llm_cache_key(model_id, prompt)

    def _get_adapter(self):
        """Return the cache adapter, initialising the Redis singleton if needed."""
        if self._cache is None:
            from backend.infrastructure.cache.redis_cache_adapter import get_redis_cache
            self._cache = get_redis_cache()
        return self._cache

    def _default_ttl(self) -> int:
        from backend.config.settings import get_settings
        return get_settings().agent_llm_cache_ttl_seconds
