"""Cross-cutting utility functions — pure stdlib, zero I/O.

new_uuid()               → str   (uuid4 as string)
llm_cache_key(model, prompt) → str  (SHA-256 hex for Redis cache keys)
content_hash(data: bytes)    → str  (SHA-256 hex for checksum dedup)
utcnow()                 → datetime (timezone-aware UTC)
format_iso(dt)           → str   (ISO 8601)
parse_iso(s)             → datetime
"""

from backend.shared.utils.datetime_utils import format_iso, parse_iso, utcnow
from backend.shared.utils.hash_utils import content_hash, llm_cache_key
from backend.shared.utils.uuid_factory import new_uuid

__all__ = ["new_uuid", "llm_cache_key", "content_hash", "utcnow", "format_iso", "parse_iso"]
