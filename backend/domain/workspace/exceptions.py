"""Workspace bounded context exceptions."""

from __future__ import annotations

from backend.shared.exceptions import DomainError


class WorkspaceError(DomainError):
    """Base exception for the workspace bounded context."""


class ConversationNotFoundError(WorkspaceError):
    def __init__(self, conversation_id: str) -> None:
        super().__init__(
            f"Conversation '{conversation_id}' not found.",
            code="CONVERSATION_NOT_FOUND",
        )
        self.conversation_id = conversation_id


class ProjectNotFoundError(WorkspaceError):
    def __init__(self, project_id: str) -> None:
        super().__init__(
            f"Project '{project_id}' not found.",
            code="PROJECT_NOT_FOUND",
        )
        self.project_id = project_id


class MessageNotFoundError(WorkspaceError):
    def __init__(self, message_id: str) -> None:
        super().__init__(
            f"Message '{message_id}' not found.",
            code="MESSAGE_NOT_FOUND",
        )
        self.message_id = message_id


class ConversationClosedError(WorkspaceError):
    """Raised when a message is appended to a conversation that has been closed."""

    def __init__(self, conversation_id: str) -> None:
        super().__init__(
            f"Conversation '{conversation_id}' is closed and cannot accept new messages.",
            code="CONVERSATION_CLOSED",
        )
        self.conversation_id = conversation_id


class DatasetMismatchError(WorkspaceError):
    """Raised when a message references a different dataset than the conversation was
    created for — prevents cross-dataset context pollution in the memory buffer.
    """

    def __init__(self, conversation_dataset: str, message_dataset: str) -> None:
        super().__init__(
            f"Conversation is linked to dataset '{conversation_dataset}' "
            f"but message references dataset '{message_dataset}'.",
            code="DATASET_MISMATCH",
        )
        self.conversation_dataset = conversation_dataset
        self.message_dataset = message_dataset


class ContextWindowExceededError(WorkspaceError):
    """Raised when the conversation has too many messages to fit in the LLM context
    window and must be compressed before adding another message.
    """

    def __init__(self, message_count: int, max_messages: int) -> None:
        super().__init__(
            f"Conversation has {message_count} messages, exceeding the "
            f"{max_messages}-message limit before compression is required.",
            code="CONTEXT_WINDOW_EXCEEDED",
        )
        self.message_count = message_count
        self.max_messages = max_messages


class ProjectDatasetLimitError(WorkspaceError):
    """Raised when a project already has the maximum number of datasets."""

    def __init__(self, project_id: str, max_datasets: int) -> None:
        super().__init__(
            f"Project '{project_id}' has reached the {max_datasets}-dataset limit.",
            code="PROJECT_DATASET_LIMIT",
        )
        self.project_id = project_id
        self.max_datasets = max_datasets
