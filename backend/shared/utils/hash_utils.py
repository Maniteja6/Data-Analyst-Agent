"""Hashing utilities.

Used for:
- Dataset content checksums (SHA-256 of file bytes) to detect duplicates
  and verify upload integrity.
- LLM response cache keys (SHA-256 of model_id + prompt) to avoid
  re-calling Bedrock for identical inputs.
- Agent input/output hashes stored in agent_executions for audit trails.
"""

from __future__ import annotations

import hashlib
import json

# ---------------------------------------------------------------------------
# SHA-256 helpers
# ---------------------------------------------------------------------------


def sha256_of_bytes(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest of a byte string.

    Used for file integrity checks on uploaded datasets.

    Example::

        checksum = sha256_of_bytes(file_content)
        # '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'
    """
    return hashlib.sha256(data).hexdigest()


def sha256_of_string(text: str, encoding: str = "utf-8") -> str:
    """Return the lowercase hex SHA-256 digest of a UTF-8 string.

    Used for LLM cache key generation and prompt deduplication.
    """
    return hashlib.sha256(text.encode(encoding)).hexdigest()


def sha256_of_dict(data: dict) -> str:
    """Return a stable SHA-256 digest of a dictionary.

    Keys are sorted before hashing so that insertion order does not
    affect the result. Non-serialisable values are coerced to strings
    via ``default=str``.

    Used to hash agent inputs and outputs for the audit log.
    """
    canonical = json.dumps(data, sort_keys=True, default=str)
    return sha256_of_string(canonical)


# ---------------------------------------------------------------------------
# Convenience: cache key builder
# ---------------------------------------------------------------------------


def llm_cache_key(model_id: str, prompt: str) -> str:
    """Build a stable cache key for an LLM (model, prompt) pair.

    Stored in Redis as ``llm_cache:<hash>`` by ``LLMResponseCache``.
    """
    return sha256_of_string(f"{model_id}:{prompt}")


def file_chunk_key(dataset_id: str, chunk_index: int) -> str:
    """Build a deterministic Qdrant point ID for a dataset text chunk.

    Qdrant point IDs must be stable across re-indexing runs so that
    upserting the same chunk twice is idempotent.
    """
    return sha256_of_string(f"{dataset_id}:chunk:{chunk_index}")


# ---------------------------------------------------------------------------
# Truncated hash (short IDs)
# ---------------------------------------------------------------------------


def short_hash(text: str, length: int = 8) -> str:
    """Return the first ``length`` hex characters of the SHA-256 of ``text``.

    Useful for generating short, human-readable correlation codes.
    Not suitable for security-sensitive use cases.
    """
    if not 1 <= length <= 64:
        raise ValueError(f"length must be between 1 and 64, got {length}")
    return sha256_of_string(text)[:length]
