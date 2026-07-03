"""Redis cache adapter — production implementation of ICacheService.

Backs:
- LLM response cache (24-hour TTL, keyed by SHA-256 of model_id + prompt)
- Insight report cache (24-hour TTL, keyed by dataset_id)
- Job status cache (1-hour TTL, keyed by job_id)
- WebSocket pub/sub fan-out (no TTL, fire-and-forget publish)
- Rate limiting (60-second sliding window, keyed by client IP)
- Conversation memory buffer (7-day TTL, keyed by conversation_id)

The adapter uses ``redis.asyncio`` (async) throughout so it never blocks
the FastAPI event loop. A single connection pool is shared via the
``@lru_cache`` singleton, meaning all coroutines in one worker process
share the same pool.

TLS note: In staging/production the ``redis_url`` uses ``rediss://``
(with double-s) and the AUTH token from Secrets Manager is embedded.
In local dev it uses plain ``redis://`` with no auth.

Usage::

    from backend.infrastructure.cache.redis_cache_adapter import get_redis_cache

    cache = get_redis_cache()
    await cache.set("key", "value", ttl=3600)
    value = await cache.get("key")
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class RedisCacheAdapter:
    """Async Redis cache adapter.

    All public methods are fully async so they can be awaited inside
    FastAPI route handlers and Celery async tasks without blocking.
    """

    def __init__(self, redis_client=None, default_ttl: int = 86400) -> None:
        """
        Args:
            redis_client: Pre-built ``redis.asyncio.Redis`` instance.
                          When None, the singleton is created from Settings.
            default_ttl:  Default key expiry in seconds (24 hours).
        """
        self._redis      = redis_client
        self._default_ttl = default_ttl

    # ── Connection ────────────────────────────────────────────────────────

    async def _get_redis(self):
        """Return the Redis client, creating it lazily on first use."""
        if self._redis is None:
            import redis.asyncio as aioredis
            from backend.config.settings import get_settings
            settings = get_settings()
            self._redis = aioredis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
            )
        return self._redis

    async def ping(self) -> bool:
        """Return True if Redis is reachable (used by the /ready health endpoint)."""
        try:
            client = await self._get_redis()
            return await client.ping()
        except Exception as exc:
            logger.warning("redis_ping_failed", error=str(exc))
            return False

    async def close(self) -> None:
        """Close the Redis connection pool."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    # ── String get / set ─────────────────────────────────────────────────

    async def get(self, key: str) -> str | None:
        """Return the raw string value for ``key``, or None if missing / expired."""
        try:
            client = await self._get_redis()
            return await client.get(key)
        except Exception as exc:
            logger.warning("redis_get_failed", key=key, error=str(exc))
            return None

    async def set(
        self, key: str, value: str, ttl: int | None = None
    ) -> None:
        """Set a string value with an optional TTL.

        Args:
            key:   Cache key.
            value: String value to store.
            ttl:   Expiry in seconds. Defaults to ``default_ttl`` when None.
        """
        try:
            client = await self._get_redis()
            await client.setex(key, ttl or self._default_ttl, value)
        except Exception as exc:
            logger.warning("redis_set_failed", key=key, error=str(exc))

    async def set_no_expiry(self, key: str, value: str) -> None:
        """Set a value without an expiry (persists until explicitly deleted)."""
        try:
            client = await self._get_redis()
            await client.set(key, value)
        except Exception as exc:
            logger.warning("redis_set_no_expiry_failed", key=key, error=str(exc))

    # ── JSON helpers ──────────────────────────────────────────────────────

    async def get_json(self, key: str) -> dict | list | None:
        """Retrieve and deserialise a JSON-encoded value.

        Returns None when the key is missing, expired, or contains invalid JSON.
        """
        raw = await self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("redis_json_decode_failed", key=key, error=str(exc))
            return None

    async def set_json(
        self, key: str, value: dict | list, ttl: int | None = None
    ) -> None:
        """Serialise ``value`` to JSON and store it.

        Non-serialisable values are coerced to strings via ``default=str``.
        """
        try:
            encoded = json.dumps(value, default=str)
        except (TypeError, ValueError) as exc:
            logger.warning("redis_json_encode_failed", key=key, error=str(exc))
            return
        await self.set(key, encoded, ttl)

    # ── Existence and deletion ────────────────────────────────────────────

    async def exists(self, key: str) -> bool:
        """Return True when the key exists and has not expired."""
        try:
            client = await self._get_redis()
            return bool(await client.exists(key))
        except Exception:
            return False

    async def delete(self, key: str) -> None:
        """Delete a key (no-op if the key does not exist)."""
        try:
            client = await self._get_redis()
            await client.delete(key)
        except Exception as exc:
            logger.warning("redis_delete_failed", key=key, error=str(exc))

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a glob pattern. Returns the number of deleted keys.

        Use sparingly — ``SCAN`` is used internally to avoid blocking the Redis
        server, but large keyspaces still incur latency.

        Example: ``await cache.delete_pattern("insights:*")``
        """
        try:
            client = await self._get_redis()
            keys = [key async for key in client.scan_iter(match=pattern)]
            if keys:
                return await client.delete(*keys)
            return 0
        except Exception as exc:
            logger.warning("redis_delete_pattern_failed", pattern=pattern, error=str(exc))
            return 0

    async def ttl(self, key: str) -> int:
        """Return remaining TTL in seconds. -1 = no expiry, -2 = key not found."""
        try:
            client = await self._get_redis()
            return await client.ttl(key)
        except Exception:
            return -2

    # ── Atomic increment (rate limiting) ─────────────────────────────────

    async def incr(self, key: str, ttl: int | None = None) -> int:
        """Atomically increment a counter and return the new value.

        If the key does not exist it is created with value 1.
        When ``ttl`` is provided and the key is new, ``EXPIRE`` is set.

        Used by ``RateLimitMiddleware``:
            count = await cache.incr(f"rate_limit:{client_ip}", ttl=60)
            if count > LIMIT: return 429
        """
        try:
            client = await self._get_redis()
            pipe   = client.pipeline()
            pipe.incr(key)
            if ttl:
                pipe.expire(key, ttl, xx=False)  # only set expiry if not already set
            results = await pipe.execute()
            return int(results[0])
        except Exception as exc:
            logger.warning("redis_incr_failed", key=key, error=str(exc))
            return 0

    # ── Pub / sub (WebSocket fan-out) ─────────────────────────────────────

    async def publish(self, channel: str, message: str) -> int:
        """Publish a message to a Redis pub/sub channel.

        Returns the number of subscribers that received the message.

        Used by the analytics pipeline workers to notify the WebSocket
        gateway without a direct coupling to Socket.IO:
            await cache.publish(f"dataset:{dataset_id}", json.dumps(event))
        """
        try:
            client = await self._get_redis()
            return await client.publish(channel, message)
        except Exception as exc:
            logger.warning("redis_publish_failed", channel=channel, error=str(exc))
            return 0

    async def publish_json(self, channel: str, payload: dict) -> int:
        """Serialise ``payload`` to JSON and publish to a channel."""
        return await self.publish(channel, json.dumps(payload, default=str))

    # ── Hash operations (job status tracking) ────────────────────────────

    async def hset(self, key: str, mapping: dict[str, Any], ttl: int | None = None) -> None:
        """Store a hash (dict) under ``key``."""
        try:
            client = await self._get_redis()
            await client.hset(key, mapping={k: str(v) for k, v in mapping.items()})
            if ttl:
                await client.expire(key, ttl)
        except Exception as exc:
            logger.warning("redis_hset_failed", key=key, error=str(exc))

    async def hgetall(self, key: str) -> dict[str, str]:
        """Return all fields of a hash, or an empty dict if not found."""
        try:
            client = await self._get_redis()
            return await client.hgetall(key)
        except Exception:
            return {}

    async def hset_field(self, key: str, field: str, value: str) -> None:
        """Set a single field in a hash."""
        try:
            client = await self._get_redis()
            await client.hset(key, field, value)
        except Exception as exc:
            logger.warning("redis_hset_field_failed", key=key, field=field, error=str(exc))

    # ── Convenience domain helpers ────────────────────────────────────────

    async def cache_job_status(
        self,
        job_id: str,
        status: str,
        progress: int = 0,
        step: str = "",
        extra: dict | None = None,
    ) -> None:
        """Write a job status entry used by the ``GetJobStatusUseCase``.

        Keys are stored as hashes under ``job:<job_id>`` with a 1-hour TTL.
        The ``/api/v1/jobs/<job_id>`` endpoint calls ``hgetall`` to read them.
        """
        payload = {
            "job_id":   job_id,
            "status":   status,
            "progress": str(progress),
            "step":     step,
            **(extra or {}),
        }
        await self.hset(f"job:{job_id}", payload, ttl=3600)

    async def get_job_status(self, job_id: str) -> dict:
        """Read a job status entry by job_id."""
        data = await self.hgetall(f"job:{job_id}")
        if data and "progress" in data:
            data["progress"] = int(data["progress"])
        return data

    async def invalidate_insights(self, dataset_id: str) -> None:
        """Delete the insight cache entry for a dataset.

        Called by ``on_insight_report_generated`` event handler after the
        InsightAgent completes so the next GET request fetches fresh data.
        """
        await self.delete(f"insights:{dataset_id}")
        logger.info("insights_cache_invalidated", dataset_id=dataset_id)


@lru_cache(maxsize=1)
def get_redis_cache() -> RedisCacheAdapter:
    """Return the cached RedisCacheAdapter singleton.

    Call ``get_redis_cache.cache_clear()`` in tests that need a fresh adapter.
    """
    from backend.config.settings import get_settings
    settings = get_settings()
    return RedisCacheAdapter(default_ttl=settings.redis_ttl_seconds)
