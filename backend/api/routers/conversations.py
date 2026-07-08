"""Conversation CRUD and chat endpoints."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import structlog
from backend.api.dependencies import (
    get_conversation_repo,
    get_create_conversation_use_case,
    get_send_message_use_case,
)
from backend.api.schemas.conversation_schemas import (
    ConversationResponse,
    CreateConversationRequest,
    CreateConversationResponse,
    MessageResponse,
    SendMessageRequest,
)
from backend.application.commands.send_message_command import SendMessageCommand
from fastapi import APIRouter, Depends, HTTPException

if TYPE_CHECKING:
    from backend.application.use_cases.create_conversation import CreateConversationUseCase
    from backend.application.use_cases.send_message import SendMessageUseCase
    from backend.domain.workspace.repositories.conversation_repository import (
        ConversationRepository,
    )

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.post("/", response_model=CreateConversationResponse, status_code=201)
async def create_conversation(
    body: CreateConversationRequest,
    use_case: CreateConversationUseCase = Depends(get_create_conversation_use_case),
) -> CreateConversationResponse:
    """Create a new conversation for a dataset."""
    result = await use_case.execute(dataset_id=body.dataset_id, title=body.title)
    return CreateConversationResponse(**result)


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    repo: ConversationRepository = Depends(get_conversation_repo),
) -> ConversationResponse:
    """Retrieve a conversation with its message history."""
    conv = await repo.get_by_id(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return ConversationResponse(
        id=conv.id,
        dataset_id=conv.dataset_id,
        title=conv.title,
        message_count=conv.message_count,
        is_closed=conv.is_closed,
        created_at=conv.created_at.isoformat() if conv.created_at else None,
        updated_at=conv.updated_at.isoformat() if conv.updated_at else None,
        messages=[m.to_dict() for m in conv.messages],
    )


@router.post("/{conversation_id}/messages", response_model=MessageResponse)
async def send_message(
    conversation_id: str,
    body: SendMessageRequest,
    use_case: SendMessageUseCase = Depends(get_send_message_use_case),
) -> MessageResponse:
    """Send a user message and receive the AI assistant's response."""
    conv = await use_case._conv_repo.get_by_id(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    cmd = SendMessageCommand(
        conversation_id=conversation_id,
        dataset_id=conv.dataset_id,
        content=body.content,
        correlation_id=str(uuid.uuid4()),
        stream=body.stream,
    )
    result = await use_case.execute(cmd)
    return MessageResponse(**result)


@router.get("/by-dataset/{dataset_id}", response_model=list[ConversationResponse])
async def list_conversations(
    dataset_id: str,
    repo: ConversationRepository = Depends(get_conversation_repo),
) -> list[ConversationResponse]:
    """List all conversations for a dataset."""
    convs = await repo.get_by_dataset_id(dataset_id)
    return [
        ConversationResponse(
            id=c.id,
            dataset_id=c.dataset_id,
            title=c.title,
            message_count=c.message_count,
            is_closed=c.is_closed,
            created_at=c.created_at.isoformat() if c.created_at else None,
            updated_at=c.updated_at.isoformat() if c.updated_at else None,
        )
        for c in convs
    ]
