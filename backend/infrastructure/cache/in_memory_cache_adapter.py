"""In-memory cache adapter — drop-in Redis replacement for tests and local dev.

Used in two contexts:

1. **Unit and integration tests** — injected via the ``api/dependencies.py``
   ``get_redis_cache`` override so tests never need a running Redis server.
   ``fakeredis`` is also an option but this implementation has zero extra
   dependencies and is simpler to inspect in test assertions.

2. **Local development without Docker** — set ``REDIS_URL=memory://`` and
   the ``api/dependencies.py`` factory returns this adapter instead.

Thread-safety: Uses a single dict + expiry dict protected by ``asyncio.Lock``.
Safe for use inside an asyncio event loop but not across OS threads.

Limitations vs Redis:
- Pub/sub ``publish()`` is a no-op (no subscribers in-process)
- ``delete_pattern()`` does a full scan of all keys
- ``hset``/``hgetall`` are backed by nested dicts (not Redis hashes)
- Data is lost on process restart / between test cases unless ``clear()`` is called

Usage in tests::

    from backend.infrastructure.cache.in_memory_cache_adapter import InMemoryCacheAdapter

    cache = InMemoryCacheAdapter()
    await cache.set("key", "value", ttl=60)
    assert await cache.get("key") == "value"
    cache.clear()
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import time
from typing import Any

from backend.application.ports.cache_port import ICacheService


class InMemoryCacheAdapter(ICacheService):
    """Thread-safe async in-memory cache with TTL support.

    All public methods match the ``RedisCacheAdapter`` interface so the
    two adapters are interchangeable at injection sites.
    """

    def __init__(self, default_ttl: int = 86400) -> None:
        self._store: dict[str, str] = {}  # key → raw string value
        self._expiry: dict[str, float] = {}  # key → unix timestamp of expiry
        self._hashes: dict[str, dict[str, str]] = {}  # key → {field: value} for hset
        self._lock = asyncio.Lock()
        self._default_ttl = default_ttl

    # ── TTL helpers ───────────────────────────────────────────────────────

    def _is_expired(self, key: str) -> bool:
        expiry = self._expiry.get(key)
        if expiry is None:
            return False
        return time.time() > expiry

    def _evict(self, key: str) -> None:
        """Remove a key that has expired."""
        self._store.pop(key, None)
        self._expiry.pop(key, None)
        self._hashes.pop(key, None)

    def _set_expiry(self, key: str, ttl: int) -> None:
        self._expiry[key] = time.time() + ttl

    # ── Ping / teardown ───────────────────────────────────────────────────

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        """No-op — in-memory adapter has no connection to close."""

    # ── String get / set ─────────────────────────────────────────────────

    async def get(self, key: str) -> str | None:
        async with self._lock:
            if self._is_expired(key):
                self._evict(key)
                return None
            return self._store.get(key)

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        async with self._lock:
            self._store[key] = value
            self._set_expiry(key, ttl or self._default_ttl)

    async def set_no_expiry(self, key: str, value: str) -> None:
        async with self._lock:
            self._store[key] = value
            self._expiry.pop(key, None)

    # ── JSON helpers ──────────────────────────────────────────────────────

    async def get_json(self, key: str) -> dict | list | None:
        raw = await self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def set_json(self, key: str, value: dict | list, ttl: int | None = None) -> None:
        await self.set(key, json.dumps(value, default=str), ttl)

    # ── Existence and deletion ────────────────────────────────────────────

    async def exists(self, key: str) -> bool:
        async with self._lock:
            if self._is_expired(key):
                self._evict(key)
                return False
            return key in self._store

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._evict(key)

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a glob pattern. Returns the count deleted."""
        async with self._lock:
            matched = [k for k in list(self._store.keys()) if fnmatch.fnmatch(k, pattern)]
            for key in matched:
                self._evict(key)
            return len(matched)

    async def ttl(self, key: str) -> int:
        async with self._lock:
            if self._is_expired(key):
                self._evict(key)
                return -2
            expiry = self._expiry.get(key)
            if expiry is None:
                return -1 if key in self._store else -2
            return max(0, int(expiry - time.time()))

    # ── Atomic increment ──────────────────────────────────────────────────

    async def incr(self, key: str, ttl: int | None = None) -> int:
        async with self._lock:
            if self._is_expired(key):
                self._evict(key)
            current = int(self._store.get(key, "0"))
            new_val = current + 1
            self._store[key] = str(new_val)
            if ttl and key not in self._expiry:
                self._set_expiry(key, ttl)
            return new_val

    # ── Pub / sub (no-op) ─────────────────────────────────────────────────

    async def publish(self, channel: str, message: str) -> int:
        """No-op — in-memory adapter has no pub/sub subscribers."""
        return 0

    async def publish_json(self, channel: str, payload: dict) -> int:
        return 0

    # ── Hash operations ───────────────────────────────────────────────────

    async def hset(self, key: str, mapping: dict[str, Any], ttl: int | None = None) -> None:
        async with self._lock:
            existing = self._hashes.setdefault(key, {})
            existing.update({k: str(v) for k, v in mapping.items()})
            if ttl:
                self._set_expiry(key, ttl)

    async def hgetall(self, key: str) -> dict[str, str]:
        async with self._lock:
            if self._is_expired(key):
                self._evict(key)
                return {}
            return dict(self._hashes.get(key, {}))

    async def hset_field(self, key: str, field: str, value: str) -> None:
        async with self._lock:
            self._hashes.setdefault(key, {})[field] = value

    # ── Domain helpers (mirror RedisCacheAdapter) ─────────────────────────

    async def cache_job_status(
        self,
        job_id: str,
        status: str,
        progress: int = 0,
        step: str = "",
        extra: dict | None = None,
    ) -> None:
        payload = {
            "job_id": job_id,
            "status": status,
            "progress": str(progress),
            "step": step,
            **(extra or {}),
        }
        await self.hset(f"job:{job_id}", payload, ttl=3600)

    async def get_job_status(self, job_id: str) -> dict:
        data = await self.hgetall(f"job:{job_id}")
        result: dict[str, Any] = dict(data)
        if "progress" in result:
            result["progress"] = int(result["progress"])
        return result

    async def invalidate_insights(self, dataset_id: str) -> None:
        await self.delete(f"insights:{dataset_id}")

    # ── Test helpers ───────────────────────────────────────────────────────

    def clear(self) -> None:
        """Wipe all keys — call between test cases to prevent state leakage."""
        self._store.clear()
        self._expiry.clear()
        self._hashes.clear()

    def keys(self) -> list[str]:
        """Return all currently live (non-expired) keys — useful in test assertions."""
        now = time.time()
        return [k for k in self._store if k not in self._expiry or self._expiry[k] > now]

    def size(self) -> int:
        """Return the number of live keys."""
        return len(self.keys())
