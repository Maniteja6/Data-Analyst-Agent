"""Cache adapters — Redis (production) and in-memory (tests/dev)."""
"""Cache adapters — Redis (production) and in-memory (tests).

RedisCacheAdapter:    get/set/get_json/set_json/publish_json/cache_job_status/
                      get_job_status/invalidate_insights/delete_pattern/ping.
InMemoryCacheAdapter: identical interface; dict-backed; clear() for test teardown.

Real-time role:
    publish_json(channel, payload) is the single call that drives all
    real-time UI updates — workers publish, Socket.IO bridge subscribes.
"""
from backend.infrastructure.cache.redis_cache_adapter     import RedisCacheAdapter
from backend.infrastructure.cache.in_memory_cache_adapter import InMemoryCacheAdapter

__all__ = ["RedisCacheAdapter", "InMemoryCacheAdapter"]
