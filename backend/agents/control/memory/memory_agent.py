"""MemoryAgent — manages conversation context window and Redis-backed session memory.

Real-time design:
    The MemoryAgent runs at two points in the chat pipeline:
    1. PRE-EXECUTE: called by the chat handler BEFORE invoking the LLM.
       Restores the message buffer from Redis so a reconnected WebSocket
       client immediately gets full conversation context.
    2. POST-EXECUTE: called AFTER the assistant response to decide whether
       to compress history and persist to Redis.

    Both operations are async and non-blocking. Failures are soft — the
    pipeline continues even if Redis is unavailable.
"""
from __future__ import annotations

from typing import Any

import structlog
from backend.agents.base.agent_context import AgentContext
from backend.agents.base.base_agent import BaseAgent
from backend.agents.control.memory.conversation_compressor import ConversationCompressor
from backend.agents.control.memory.episodic_store import EpisodicStore

logger = structlog.get_logger(__name__)


class MemoryAgent(BaseAgent):
    """Manages conversation history compression and Redis persistence.

    Args:
        llm_client:   LLM client for compression (can be None in tests).
        redis_client: Cache adapter for episodic storage (can be None in tests).
    """

    def __init__(self, llm_client: Any = None, redis_client: Any = None) -> None:
        super().__init__("memory")
        self._compressor = ConversationCompressor(llm_client)
        self._store      = EpisodicStore(redis_client)

    # ── Agent execute (post-message, called by pipeline) ──────────────────

    async def _execute(
        self,
        context: AgentContext,
        conversation_id: str = "",
        new_user_message: dict | None = None,
        new_assistant_message: dict | None = None,
        **kwargs: Any,
    ) -> dict:
        """Process memory after one round-trip of chat.

        Steps:
            1. Append new user + assistant messages to the buffer
            2. If buffer is long, compress and replace
            3. Save updated buffer to Redis
            4. Update AgentContext.conversation_history for the next turn

        Args:
            context:               Shared pipeline state.
            conversation_id:       Conversation UUID (Redis key prefix).
            new_user_message:      Bedrock Converse user message dict.
            new_assistant_message: Bedrock Converse assistant message dict.

        Returns:
            Dict with keys: compressed, summary, message_count.
        """
        if not conversation_id:
            return {"compressed": False, "summary": "", "message_count": 0}

        # Load current buffer from Redis (handles reconnects)
        messages = await self._store.get_messages(conversation_id)
        if not messages:
            messages = list(context.conversation_history)

        # Append new messages
        if new_user_message:
            messages.append(new_user_message)
        if new_assistant_message:
            messages.append(new_assistant_message)

        compressed = False
        summary    = ""

        # Compress when approaching the context limit
        if self._compressor.needs_compression(messages):
            messages   = await self._compressor.compress_and_replace(messages)
            compressed = True
            summary    = self._extract_summary(messages)
            await self._store.save_memory(conversation_id, summary)
            logger.info(
                "memory_compressed",
                conversation_id=conversation_id,
                messages_after=len(messages),
            )

        # Persist and update context
        await self._store.save_messages(conversation_id, messages)
        context.conversation_history = messages

        return {
            "compressed":    compressed,
            "summary":       summary,
            "message_count": len(messages),
        }

    # ── Pre-execute: restore history on reconnect ─────────────────────────

    async def restore_session(
        self,
        context: AgentContext,
        conversation_id: str,
    ) -> list[dict]:
        """Restore conversation history from Redis.

        Called by the WebSocket chat handler when a client reconnects or
        resumes an existing conversation.

        Returns:
            The full message list (may be empty for new conversations).
        """
        messages = await self._store.get_messages(conversation_id)
        if messages:
            context.conversation_history = messages
            logger.info(
                "session_restored",
                conversation_id=conversation_id,
                message_count=len(messages),
            )
        return messages

    async def init_session(
        self,
        conversation_id: str,
        dataset_id: str,
        system_prompt: str = "",
    ) -> None:
        """Initialise a new conversation session in Redis.

        Called by CreateConversationUseCase immediately after persisting
        the Conversation aggregate to Postgres.
        """
        await self._store.initialise_session(
            conversation_id=conversation_id,
            dataset_id=dataset_id,
            system_prompt=system_prompt,
        )

    async def delete_session(self, conversation_id: str) -> None:
        """Delete all Redis keys for a conversation (GDPR / end of session)."""
        await self._store.delete_session(conversation_id)

    @staticmethod
    def _extract_summary(messages: list[dict]) -> str:
        """Extract the summary text from the injected summary block."""
        if messages and messages[0].get("role") == "user":
            content = messages[0].get("content", [])
            if content and isinstance(content, list):
                text = content[0].get("text", "")
                if text.startswith("[Context from prior conversation]"):
                    return text.replace("[Context from prior conversation]\n", "")
        return ""
