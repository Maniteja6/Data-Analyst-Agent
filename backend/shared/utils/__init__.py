"""Cross-cutting utility functions — pure stdlib, zero I/O.

new_uuid()                   → str   (uuid4 as string)
llm_cache_key(model, prompt) → str   (SHA-256 hex for Redis cache keys)
sha256_of_bytes(data: bytes) → str   (SHA-256 hex for checksum dedup)
utcnow()                     → datetime (timezone-aware UTC)
to_iso8601(dt)                → str   (ISO 8601)
from_iso8601(s)                → datetime
"""

from backend.shared.utils.datetime_utils import from_iso8601, to_iso8601, utcnow
from backend.shared.utils.hash_utils import llm_cache_key, sha256_of_bytes
from backend.shared.utils.uuid_factory import new_uuid

__all__ = ["new_uuid", "llm_cache_key", "sha256_of_bytes", "utcnow", "to_iso8601", "from_iso8601"]
