"""ConversationCompressor — reduces conversation history to stay within context limits.

Real-time design:
    For live chat, compressing old turns prevents the context window from
    overflowing mid-conversation. The compressed summary is stored in
    Redis so it survives WebSocket disconnections and reconnects.

Compression strategy:
    When message count ≥ MAX_TURNS_BEFORE_COMPRESS, the oldest messages
    (all except the last KEEP_RECENT_TURNS) are summarised into a single
    assistant context block. The summary is prepended as a "system" turn
    so subsequent messages benefit from the prior conversation's facts.
"""

from __future__ import annotations

import structlog
from alembic.environment import Any
from backend.infrastructure.llm.model_id_registry import get_model_id

logger = structlog.get_logger(__name__)

MAX_TURNS_BEFORE_COMPRESS = 10
KEEP_RECENT_TURNS = 4
MAX_SUMMARY_TOKENS = 800


class ConversationCompressor:
    """Summarises conversation history to prevent context window overflow.

    Args:
        llm_client: Async LLM client for summary generation.
                    When None, a placeholder summary is used (for tests).
    """

    def __init__(self, llm_client: Any = None) -> None:
        self._llm = llm_client

    def needs_compression(self, messages: list[dict]) -> bool:
        """Return True when the message list exceeds the compression threshold."""
        return len(messages) >= MAX_TURNS_BEFORE_COMPRESS

    def split_for_compression(self, messages: list[dict]) -> tuple[list[dict], list[dict]]:
        """Split messages into (to_compress, to_keep).

        The last KEEP_RECENT_TURNS messages are always kept verbatim.
        Earlier messages are compressed into a summary.
        """
        keep_start = max(0, len(messages) - KEEP_RECENT_TURNS)
        to_compress = messages[:keep_start]
        to_keep = messages[keep_start:]
        return to_compress, to_keep

    async def compress(self, messages: list[dict]) -> str:
        """Summarise a list of messages into a compact context block.

        Args:
            messages: List of Bedrock Converse API message dicts
                      ({role: user|assistant, content: [{text: ...}]}).

        Returns:
            A single summary string representing the compressed history.
        """
        if not messages:
            return ""

        if not self._llm:
            n = len(messages)
            return f"[Prior conversation: {n} turns about this dataset were summarised here.]"

        history_text = "\n".join(f"{m['role'].upper()}: {self._extract_text(m)}" for m in messages)

        prompt = (
            "Summarise the following data analytics conversation in 4-6 sentences. "
            "Preserve: specific column names, metric values, SQL queries discussed, "
            "anomalies found, and any decisions the user made. "
            "Write in past tense from the assistant's perspective.\n\n"
            f"CONVERSATION:\n{history_text}\n\n"
            "SUMMARY:"
        )

        try:
            summary = await self._llm.complete(
                prompt=prompt,
                model_id=get_model_id("memory"),
                max_tokens=MAX_SUMMARY_TOKENS,
            )
            logger.info(
                "conversation_compressed",
                original_turns=len(messages),
                summary_chars=len(summary),
            )
            return summary.strip()
        except Exception as exc:
            logger.warning("compression_failed", error=str(exc))
            return f"[Prior conversation with {len(messages)} turns compressed due to error.]"

    async def compress_and_replace(self, messages: list[dict]) -> list[dict]:
        """Compress old turns and return a new, shorter message list.

        The returned list starts with a synthetic user message containing the
        summary, followed by the most recent KEEP_RECENT_TURNS messages.
        This preserves the alternating user/assistant structure required by
        the Bedrock Converse API.

        Args:
            messages: Full message history.

        Returns:
            Shortened message list with a summary block at the start.
        """
        to_compress, to_keep = self.split_for_compression(messages)

        if not to_compress:
            return messages

        summary = await self.compress(to_compress)

        # Inject summary as a user message so it reads naturally in context
        summary_block = {
            "role": "user",
            "content": [{"text": f"[Context from prior conversation]\n{summary}"}],
        }
        # Add a synthetic assistant acknowledgement
        ack_block = {
            "role": "assistant",
            "content": [{"text": "Understood. I have the context from our earlier discussion."}],
        }

        return [summary_block, ack_block] + to_keep

    @staticmethod
    def _extract_text(message: dict) -> str:
        """Extract plain text from a Bedrock Converse API message dict."""
        content = message.get("content", [])
        if isinstance(content, list):
            return " ".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and "text" in block
            )
        return str(content)
