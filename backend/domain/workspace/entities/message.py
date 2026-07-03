"""Message entity — one turn in a Conversation."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from backend.shared.entity import Entity
from backend.domain.workspace.value_objects.message_role import MessageRole, Role


@dataclass
class Message(Entity):
    """A single conversational turn (question or answer) in a Conversation.

    Messages are immutable after creation — the Conversation aggregate
    appends them but never mutates them. The full message list is what
    gets serialised into the Bedrock Converse ``messages`` parameter.

    Attributes:
        conversation_id: Parent Conversation UUID.
        role:            Speaker role: USER, ASSISTANT, or SYSTEM.
        content:         Raw text content of the message.
        token_count:     Approximate token count (populated post-generation).
        agent_trace:     Debug trace from the agent that produced this message:
                         which agents ran, SQL generated, RAG chunks used, etc.
                         Stored as JSON; never shown to the user in production.
        citations:       List of source references embedded in the message,
                         rendered as ``[1]`` superscripts in the frontend.
                         Each citation: ``{'source': str, 'column_name': str, 'text': str}``
        visualizations:  List of Vega-Lite spec payloads attached to this message.
                         Each: ``{'type': 'vega', 'spec': {...}, 'caption': str}``
        created_at:      UTC timestamp of message creation.
        is_streaming:    True while the assistant message is still being streamed.
                         Set to False when the ``chat:complete`` event fires.
    """

    conversation_id: str
    role:            MessageRole
    content:         str

    token_count:    int | None     = None
    agent_trace:    dict | None    = None
    citations:      list[dict]     = field(default_factory=list)
    visualizations: list[dict]     = field(default_factory=list)
    created_at:     datetime | None = None
    is_streaming:   bool            = False

    # ── Derived helpers ───────────────────────────────────────────────────

    @property
    def is_user(self) -> bool:
        return self.role.is_human

    @property
    def is_assistant(self) -> bool:
        return self.role.is_ai

    @property
    def has_visualizations(self) -> bool:
        return bool(self.visualizations)

    @property
    def has_citations(self) -> bool:
        return bool(self.citations)

    @property
    def word_count(self) -> int:
        return len(self.content.split())

    def to_bedrock_format(self) -> dict:
        """Serialise this message into the Bedrock Converse API format.

        Only USER and ASSISTANT messages can appear in the messages array.
        SYSTEM messages must be handled separately.

        Returns:
            ``{'role': 'user'/'assistant', 'content': [{'text': '...'}]}``
        """
        return {
            "role":    self.role.bedrock_role,
            "content": [{"text": self.content}],
        }

    def to_dict(self) -> dict:
        return {
            "id":              self.id,
            "conversation_id": self.conversation_id,
            "role":            str(self.role),
            "content":         self.content,
            "token_count":     self.token_count,
            "citations":       self.citations,
            "visualizations":  self.visualizations,
            "is_streaming":    self.is_streaming,
            "created_at":      self.created_at.isoformat() if self.created_at else None,
        }

    # ── Factory ───────────────────────────────────────────────────────────

    @classmethod
    def user_message(cls, conversation_id: str, content: str) -> "Message":
        from backend.shared.utils.datetime_utils import utcnow
        return cls(
            conversation_id=conversation_id,
            role=MessageRole.user(),
            content=content,
            created_at=utcnow(),
        )

    @classmethod
    def assistant_message(
        cls,
        conversation_id: str,
        content: str,
        citations: list[dict] | None = None,
        visualizations: list[dict] | None = None,
        agent_trace: dict | None = None,
    ) -> "Message":
        from backend.shared.utils.datetime_utils import utcnow
        return cls(
            conversation_id=conversation_id,
            role=MessageRole.assistant(),
            content=content,
            citations=citations or [],
            visualizations=visualizations or [],
            agent_trace=agent_trace,
            created_at=utcnow(),
        )
