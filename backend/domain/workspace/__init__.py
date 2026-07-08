"""Workspace bounded context — owns the real-time chat conversation model.

Aggregate: Conversation (messages JSONB; build_bedrock_messages();
           build_system_prompt(schema_summary, rag_context))
Entity:    Message (role, content, citations, visualizations)
VO:        MessageRole (USER | ASSISTANT | SYSTEM)
Events:    ConversationCreated, MessageSent
"""

from backend.domain.workspace.entities.conversation import Conversation
from backend.domain.workspace.entities.message import Message
from backend.domain.workspace.value_objects.message_role import MessageRole

__all__ = ["Conversation", "Message", "MessageRole"]
