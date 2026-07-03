"""Conversation aggregate root — manages the multi-turn chat lifecycle."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.shared.aggregate_root import AggregateRoot
from backend.domain.workspace.entities.message import Message
from backend.domain.workspace.value_objects.message_role import MessageRole, Role
from backend.domain.workspace.events.message_added import MessageAdded
from backend.domain.workspace.events.memory_consolidated import MemoryConsolidated
from backend.domain.workspace.exceptions import (
    ConversationClosedError,
    ContextWindowExceededError,
)

# Maximum messages before the MemoryAgent is triggered to compress
MAX_MESSAGES_BEFORE_COMPRESSION = 20

# Hard cap — prevents unbounded DB row sizes
MAX_MESSAGES_HARD_LIMIT = 200


@dataclass
class Conversation(AggregateRoot):
    """Aggregate root for a multi-turn chat session about one dataset.

    Owns the ordered list of Messages and the compressed memory buffer.
    Enforces the context window limit and triggers compression via a
    domain event when the buffer grows too large.

    Each Conversation is tied to exactly one Dataset. Cross-dataset
    comparisons are handled by the Workspace aggregate (future feature).

    Attributes:
        id:                  Conversation UUID.
        dataset_id:          The dataset this conversation is about.
        title:               Short display name shown in the sidebar.
        messages:            Ordered list of Message entities (oldest first).
        memory_summary:      Compressed summary of earlier turns, prepended
                             to the Bedrock context when the buffer overflows.
        is_closed:           True when the conversation has been archived;
                             no new messages can be added.
        created_at:          UTC timestamp of conversation creation.
        updated_at:          UTC timestamp of the last message.
    """

    id:             str
    dataset_id:     str
    title:          str              = "New conversation"
    messages:       list[Message]    = field(default_factory=list)
    memory_summary: str | None       = None
    is_closed:      bool             = False
    created_at:     datetime | None  = None
    updated_at:     datetime | None  = None

    def __post_init__(self) -> None:
        super().__init__()

    # ── Domain methods ────────────────────────────────────────────────────

    def add_message(self, message: Message) -> None:
        """Append a message and emit MessageAdded.

        Validates:
        - Conversation must not be closed
        - Hard message limit not exceeded (prevents DB bloat)

        Emits MessageAdded to trigger:
        - WebSocket fan-out (message → all connected clients in the room)
        - Kafka ``chat.message`` topic (for async processing and audit)

        Args:
            message: The Message entity to append.
        """
        if self.is_closed:
            raise ConversationClosedError(self.id)

        if len(self.messages) >= MAX_MESSAGES_HARD_LIMIT:
            raise ContextWindowExceededError(len(self.messages), MAX_MESSAGES_HARD_LIMIT)

        self.messages.append(message)
        self.updated_at = datetime.now(timezone.utc)

        self._record_event(MessageAdded(
            conversation_id=self.id,
            dataset_id=self.dataset_id,
            message_id=message.id,
            role=str(message.role),
            content_preview=message.content[:100],
        ))

        # Trigger memory compression when buffer is getting large
        if self.needs_compression:
            self._record_event(MessageAdded.__class__)   # handled by MemoryAgent via event bus

    def apply_memory_summary(self, summary: str) -> None:
        """Store a compressed memory summary and trim the message buffer.

        Called by the MemoryAgent after compression. Retains only the last
        4 turns (2 exchanges) as recent context; earlier turns are covered
        by ``memory_summary``.

        Emits MemoryConsolidated so the WebSocket gateway can notify the
        browser that the conversation context was compressed.
        """
        self.memory_summary = summary
        # Keep only the most recent turns — earlier ones are now in the summary
        self.messages = self.messages[-4:]
        self._record_event(MemoryConsolidated(
            conversation_id=self.id,
            dataset_id=self.dataset_id,
            turns_compressed=len(self.messages),
            summary_preview=summary[:80],
        ))

    def close(self) -> None:
        """Archive the conversation — no further messages accepted."""
        self.is_closed  = True
        self.updated_at = datetime.now(timezone.utc)

    def rename(self, title: str) -> None:
        """Update the conversation title (auto-set from the first user message)."""
        if not title.strip():
            raise ValueError("Conversation title must not be blank")
        self.title      = title.strip()[:200]
        self.updated_at = datetime.now(timezone.utc)

    # ── Context building ──────────────────────────────────────────────────

    def build_bedrock_messages(self) -> list[dict]:
        """Build the messages list for a Bedrock Converse API call.

        Excludes SYSTEM messages (passed separately in the ``system`` param)
        and returns only USER/ASSISTANT turns.
        """
        return [
            m.to_bedrock_format()
            for m in self.messages
            if not m.role.is_system
        ]

    def build_system_prompt(self, schema_summary: str = "", rag_context: str = "") -> str:
        """Compose the Bedrock ``system`` parameter from available context.

        Injects (in order):
        1. Memory summary (compressed earlier turns)
        2. Dataset schema summary
        3. RAG-retrieved column descriptions and profile snippets
        """
        parts: list[str] = [
            "You are DataPilot, an expert data analyst assistant. "
            "Answer questions about the user's dataset concisely and accurately. "
            "When referencing numbers or statistics, always cite the specific column name.",
        ]
        if self.memory_summary:
            parts.append(f"\n## Conversation History Summary\n{self.memory_summary}")
        if schema_summary:
            parts.append(f"\n## Dataset Schema\n{schema_summary}")
        if rag_context:
            parts.append(f"\n## Relevant Context\n{rag_context}")
        return "\n".join(parts)

    # ── Derived helpers ───────────────────────────────────────────────────

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def user_messages(self) -> list[Message]:
        return [m for m in self.messages if m.is_user]

    @property
    def assistant_messages(self) -> list[Message]:
        return [m for m in self.messages if m.is_assistant]

    @property
    def last_message(self) -> Message | None:
        return self.messages[-1] if self.messages else None

    @property
    def needs_compression(self) -> bool:
        """True when the message buffer should be handed to the MemoryAgent."""
        return len(self.messages) >= MAX_MESSAGES_BEFORE_COMPRESSION

    @property
    def total_tokens(self) -> int:
        return sum(m.token_count or 0 for m in self.messages)

    # ── Factory ───────────────────────────────────────────────────────────

    @classmethod
    def create(cls, conversation_id: str, dataset_id: str, title: str = "") -> "Conversation":
        from backend.shared.utils.datetime_utils import utcnow
        now = utcnow()
        return cls(
            id=conversation_id,
            dataset_id=dataset_id,
            title=title or "New conversation",
            created_at=now,
            updated_at=now,
        )

    def to_dict(self) -> dict:
        return {
            "id":             self.id,
            "dataset_id":     self.dataset_id,
            "title":          self.title,
            "message_count":  self.message_count,
            "is_closed":      self.is_closed,
            "needs_compression": self.needs_compression,
            "total_tokens":   self.total_tokens,
            "created_at":     self.created_at.isoformat() if self.created_at else None,
            "updated_at":     self.updated_at.isoformat() if self.updated_at else None,
        }
