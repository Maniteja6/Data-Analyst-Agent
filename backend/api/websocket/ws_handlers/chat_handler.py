"""WebSocket chat handler — processes chat messages via Socket.IO."""

from __future__ import annotations

import uuid
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def handle_chat_message(sio: Any, sid: str, data: dict) -> None:  # noqa: ANN401
    """Handle a ``chat_message`` Socket.IO event.

    Expected data:
        ``{conversation_id, dataset_id, content, stream}``

    Emits back:
        ``chat:token``    — one per streaming token (when stream=True)
        ``chat:complete`` — final message with citations and visualizations
        ``chat:error``    — on failure
    """
    conversation_id = data.get("conversation_id", "")
    dataset_id = data.get("dataset_id", "")
    content = data.get("content", "")
    stream = data.get("stream", False)

    if not conversation_id or not content:
        await sio.emit(
            "chat:error", {"message": "conversation_id and content are required"}, to=sid
        )
        return

    try:
        from backend.application.commands.send_message_command import SendMessageCommand
        from backend.application.use_cases.send_message import SendMessageUseCase
        from backend.infrastructure.cache.redis_cache_adapter import get_redis_cache
        from backend.infrastructure.llm.llm_port import BedrockLLMService
        from backend.infrastructure.persistence.database import get_session
        from backend.infrastructure.persistence.repositories.postgres_conversation_repository import (  # noqa: E501
            PostgresConversationRepository,
        )
        from backend.infrastructure.persistence.repositories.postgres_dataset_repository import (
            PostgresDatasetRepository,
        )

        async with get_session() as db_session:
            use_case = SendMessageUseCase(
                conversation_repo=PostgresConversationRepository(db_session),
                dataset_repo=PostgresDatasetRepository(db_session),
                cache=get_redis_cache(),
                llm_service=BedrockLLMService(),
            )
            cmd = SendMessageCommand(
                conversation_id=conversation_id,
                dataset_id=dataset_id,
                content=content,
                correlation_id=str(uuid.uuid4()),
                stream=stream,
            )
            result = await use_case.execute(cmd)

        await sio.emit("chat:complete", result, to=sid)
        logger.info("chat_message_handled", conversation_id=conversation_id, sid=sid)

    except Exception as exc:
        logger.error("chat_handler_error", error=str(exc), sid=sid)
        await sio.emit("chat:error", {"message": "Failed to process message."}, to=sid)
