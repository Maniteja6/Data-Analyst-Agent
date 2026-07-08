"""EpisodicStore — Redis-backed conversation memory for live chat sessions.

Designed for real-time applications where WebSocket connections can drop
and reconnect. The episodic store ensures conversation history and
compressed memory survive reconnects so users don't lose context.

Storage schema (all keys prefixed with ``dp:conv:``):
    dp:conv:<id>:messages   — JSON array of Bedrock Converse message dicts
    dp:conv:<id>:memory     — compressed summary string from ConversationCompressor
    dp:conv:<id>:meta       — lightweight metadata (dataset_id, started_at)

Default TTL: 24 hours. Refreshed on every write to keep active sessions alive.

Usage::

    store = EpisodicStore(redis_client=get_redis_cache())

    # Save after each message
    await store.save_messages(conversation_id, messages)

    # Restore on reconnect
    messages = await store.get_messages(conversation_id)
    memory   = await store.get_memory(conversation_id)
"""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_KEY_PREFIX = "dp:conv"
DEFAULT_TTL = 86_400  # 24 hours
META_TTL = 604_800  # 7 days (metadata lives longer than messages)


class EpisodicStore:
    """Redis-backed episodic memory store for conversation sessions.

    Args:
        redis_client: An async Redis/cache adapter with get/set/delete methods.
                      Accepts InMemoryCacheAdapter in tests.
    """

    def __init__(self, redis_client: Any = None) -> None:  # noqa: ANN401
        self._redis = redis_client

    # ── Message buffer ────────────────────────────────────────────────────

    async def get_messages(self, conversation_id: str) -> list[dict]:
        """Retrieve the full message buffer for a conversation.

        Returns an empty list when the session has expired or was never stored.
        """
        raw = await self._get(f"{_KEY_PREFIX}:{conversation_id}:messages")
        if not raw:
            return []
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("episodic_corrupt_messages", conversation_id=conversation_id)
            return []

    async def save_messages(
        self,
        conversation_id: str,
        messages: list[dict],
        ttl: int = DEFAULT_TTL,
    ) -> None:
        """Persist the message buffer, refreshing the TTL.

        Args:
            conversation_id: UUID of the Conversation aggregate.
            messages:        Full Bedrock Converse message list.
            ttl:             Redis TTL in seconds.
        """
        await self._set(
            f"{_KEY_PREFIX}:{conversation_id}:messages",
            json.dumps(messages, default=str),
            ttl,
        )

    async def append_message(
        self,
        conversation_id: str,
        message: dict,
        ttl: int = DEFAULT_TTL,
    ) -> list[dict]:
        """Append one message to the buffer and return the full updated list.

        Atomic-ish: loads, appends, saves. Not truly atomic but fine for
        single-user conversations (one writer per conversation_id).
        """
        messages = await self.get_messages(conversation_id)
        messages.append(message)
        await self.save_messages(conversation_id, messages, ttl)
        return messages

    # ── Compressed memory ─────────────────────────────────────────────────

    async def get_memory(self, conversation_id: str) -> str | None:
        """Retrieve the compressed memory summary.

        Returns None when no summary has been generated yet.
        """
        return await self._get(f"{_KEY_PREFIX}:{conversation_id}:memory")

    async def save_memory(
        self,
        conversation_id: str,
        summary: str,
        ttl: int = DEFAULT_TTL,
    ) -> None:
        """Persist the compressed memory summary."""
        await self._set(
            f"{_KEY_PREFIX}:{conversation_id}:memory",
            summary,
            ttl,
        )

    # ── Session metadata ──────────────────────────────────────────────────

    async def get_meta(self, conversation_id: str) -> dict:
        """Retrieve lightweight session metadata."""
        raw = await self._get(f"{_KEY_PREFIX}:{conversation_id}:meta")
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    async def save_meta(
        self,
        conversation_id: str,
        meta: dict,
        ttl: int = META_TTL,
    ) -> None:
        """Persist session metadata (dataset_id, started_at, etc.)."""
        meta.setdefault("updated_at", datetime.now(UTC).isoformat())
        await self._set(
            f"{_KEY_PREFIX}:{conversation_id}:meta",
            json.dumps(meta, default=str),
            ttl,
        )

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def initialise_session(
        self,
        conversation_id: str,
        dataset_id: str,
        system_prompt: str = "",
        ttl: int = DEFAULT_TTL,
    ) -> None:
        """Create a new session record in Redis.

        Called when CreateConversationUseCase creates a new Conversation.
        """
        await self.save_meta(
            conversation_id,
            {
                "dataset_id": dataset_id,
                "started_at": datetime.now(UTC).isoformat(),
                "message_count": 0,
            },
        )
        if system_prompt:
            await self._set(
                f"{_KEY_PREFIX}:{conversation_id}:system",
                system_prompt,
                ttl,
            )
        logger.info("episodic_session_initialised", conversation_id=conversation_id)

    async def get_system_prompt(self, conversation_id: str) -> str | None:
        """Retrieve the cached system prompt for a conversation."""
        return await self._get(f"{_KEY_PREFIX}:{conversation_id}:system")

    async def delete_session(self, conversation_id: str) -> None:
        """Delete all keys for a conversation (GDPR erasure / user logout)."""
        if not self._redis:
            return
        for suffix in ("messages", "memory", "meta", "system"):
            with contextlib.suppress(Exception):
                await self._redis.delete(f"{_KEY_PREFIX}:{conversation_id}:{suffix}")
        logger.info("episodic_session_deleted", conversation_id=conversation_id)

    # ── Private helpers ───────────────────────────────────────────────────

    async def _get(self, key: str) -> str | None:
        if not self._redis:
            return None
        try:
            return await self._redis.get(key)
        except Exception as exc:
            logger.debug("episodic_get_failed", key=key, error=str(exc))
            return None

    async def _set(self, key: str, value: str, ttl: int) -> None:
        if not self._redis:
            return
        try:
            await self._redis.set(key, value, ttl=ttl)
        except Exception as exc:
            logger.debug("episodic_set_failed", key=key, error=str(exc))
