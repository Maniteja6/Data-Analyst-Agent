"""Conversation memory — Redis episodic store + context window compression.

EpisodicStore persists message history so WebSocket reconnects restore context.
ConversationCompressor summarises old turns when count >= MAX_TURNS_BEFORE_COMPRESS.
MemoryAgent orchestrates both; called pre- and post-LLM on every chat turn.
"""

from backend.agents.control.memory.conversation_compressor import (
    ConversationCompressor,
)
from backend.agents.control.memory.episodic_store import EpisodicStore
from backend.agents.control.memory.memory_agent import MemoryAgent

__all__ = ["MemoryAgent", "EpisodicStore", "ConversationCompressor"]
