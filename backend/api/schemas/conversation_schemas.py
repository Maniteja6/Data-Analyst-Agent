"""Conversation request/response Pydantic schemas."""
from __future__ import annotations
from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    dataset_id: str
    title:      str = ""


class CreateConversationResponse(BaseModel):
    conversation_id: str
    dataset_id:      str
    title:           str
    created_at:      str | None = None


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10_000)
    stream:  bool = False


class MessageResponse(BaseModel):
    message_id:      str
    content:         str
    citations:       list[dict] = []
    visualizations:  list[dict] = []
    conversation_id: str


class ConversationResponse(BaseModel):
    id:            str
    dataset_id:    str
    title:         str
    message_count: int
    is_closed:     bool
    created_at:    str | None = None
    updated_at:    str | None = None
    messages:      list[dict] = []
