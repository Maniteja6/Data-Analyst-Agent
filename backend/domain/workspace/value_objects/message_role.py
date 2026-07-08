"""MessageRole value object — speaker role in a conversation turn."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.shared.value_object import ValueObject


class Role(str, Enum):
    """The speaker role for a conversation message.

    Mapped directly to the Bedrock Converse API ``role`` field:
    - ``USER``      — the human's input
    - ``ASSISTANT`` — the AI's response
    - ``SYSTEM``    — injected context (schema summary, RAG chunks, etc.)

    The SYSTEM role is used internally for the context injection step
    and is not stored as a regular message in the conversation history.
    """

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass(frozen=True)
class MessageRole(ValueObject):
    """Validated message role VO.

    Wraps the ``Role`` enum to give call sites a consistent type
    and prevent magic strings like ``"usr"`` from sneaking in.

    Example::

        role = MessageRole(role=Role.USER)
        assert role.is_human
        assert not role.is_ai

        # Convenience factories:
        user_role      = MessageRole.user()
        assistant_role = MessageRole.assistant()
    """

    role: Role

    # ── Convenience factories ─────────────────────────────────────────────

    @classmethod
    def user(cls) -> MessageRole:
        return cls(role=Role.USER)

    @classmethod
    def assistant(cls) -> MessageRole:
        return cls(role=Role.ASSISTANT)

    @classmethod
    def system(cls) -> MessageRole:
        return cls(role=Role.SYSTEM)

    @classmethod
    def from_string(cls, value: str) -> MessageRole:
        """Parse a string like ``'user'`` into a MessageRole."""
        return cls(role=Role(value.lower()))

    # ── Derived helpers ───────────────────────────────────────────────────

    @property
    def is_human(self) -> bool:
        return self.role == Role.USER

    @property
    def is_ai(self) -> bool:
        return self.role == Role.ASSISTANT

    @property
    def is_system(self) -> bool:
        return self.role == Role.SYSTEM

    @property
    def bedrock_role(self) -> str:
        """Returns the role string expected by the Bedrock Converse API.

        Bedrock only accepts ``'user'`` and ``'assistant'`` in the messages array.
        SYSTEM messages must be passed in the separate ``system`` parameter.
        """
        if self.role == Role.SYSTEM:
            raise ValueError(
                "SYSTEM role cannot be used in the Bedrock Converse messages array. "
                "Pass it in the 'system' parameter instead."
            )
        return self.role.value

    def __str__(self) -> str:
        return self.role.value
