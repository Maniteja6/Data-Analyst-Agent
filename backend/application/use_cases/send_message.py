"""SendMessageUseCase — processes a user chat message and returns the AI response."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from backend.application.commands.send_message_command import SendMessageCommand
from backend.domain.workspace.entities.message import Message
from backend.domain.workspace.exceptions import ConversationNotFoundError

if TYPE_CHECKING:
    from backend.domain.dataset.repositories.dataset_repository import DatasetRepository
    from backend.domain.workspace.repositories.conversation_repository import (
        ConversationRepository,
    )
    from backend.infrastructure.cache.redis_cache_adapter import RedisCacheAdapter
    from backend.infrastructure.llm.llm_port import ILLMService

logger = structlog.get_logger(__name__)


class SendMessageUseCase:
    """Appends a user message to the conversation, invokes the chat query graph,
    appends the assistant response, and persists the updated conversation.
    """

    def __init__(
        self,
        conversation_repo: ConversationRepository,
        dataset_repo: DatasetRepository,
        cache: RedisCacheAdapter,
        llm_service: ILLMService,
    ) -> None:
        self._conv_repo = conversation_repo
        self._dataset_repo = dataset_repo
        self._cache = cache
        self._llm = llm_service

    async def execute(self, cmd: SendMessageCommand) -> dict:
        # Load conversation
        conversation = await self._conv_repo.get_by_id(cmd.conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(cmd.conversation_id)

        # Load dataset for storage key
        dataset = await self._dataset_repo.get_by_id(cmd.dataset_id)
        if dataset is None:
            from backend.domain.dataset.exceptions import DatasetNotFoundError

            raise DatasetNotFoundError(cmd.dataset_id)

        # Load insight report for system prompt context
        insight_summary = ""
        cached_report = await self._cache.get_json(f"insights:{cmd.dataset_id}")
        if cached_report:
            insight_summary = cached_report.get("executive_summary", "")

        # Append user message
        user_msg = Message.user_message(cmd.conversation_id, cmd.content)
        conversation.add_message(user_msg)

        # Build system prompt
        schema_summary = _build_schema_summary(dataset.schema_json)
        system_prompt = conversation.build_system_prompt(
            schema_summary=schema_summary,
            rag_context=insight_summary,
        )

        # Invoke the chat query graph
        from backend.orchestration.graphs.chat_query_graph import build_chat_query_graph
        from backend.orchestration.state.chat_state import ChatState

        initial_state: ChatState = {
            "user_message": cmd.content,
            "conversation_id": cmd.conversation_id,
            "dataset_id": cmd.dataset_id,
            "session_id": "",
            "correlation_id": cmd.correlation_id,
            "messages": conversation.build_bedrock_messages(),
            "system_prompt": system_prompt,
            "errors": [],
            "metadata": {},
        }

        graph = build_chat_query_graph()
        final_state = await graph.ainvoke(initial_state)
        response_text = final_state.get("assistant_response", "I was unable to process your query.")
        citations = final_state.get("citations", [])
        visualizations = final_state.get("visualizations", [])

        # Append assistant message
        assistant_msg = Message.assistant_message(
            conversation_id=cmd.conversation_id,
            content=response_text,
            citations=citations,
            visualizations=visualizations,
        )
        conversation.add_message(assistant_msg)

        # Persist
        await self._conv_repo.save(conversation)

        # Publish events
        for event in conversation.pull_domain_events():
            try:
                from backend.infrastructure.messaging.kafka_event_bus import KafkaEventBus

                async with KafkaEventBus() as bus:
                    await bus.publish(event, partition_key=cmd.dataset_id)
            except Exception as exc:
                logger.debug("domain_event_publish_failed", error=str(exc))  # non-critical

        logger.info(
            "message_processed",
            conversation_id=cmd.conversation_id,
            response_length=len(response_text),
        )
        return {
            "message_id": assistant_msg.id,
            "content": response_text,
            "citations": citations,
            "visualizations": visualizations,
            "conversation_id": cmd.conversation_id,
        }


def _build_schema_summary(schema_json: dict | None) -> str:
    """Build a compact schema summary string for the system prompt."""
    if not schema_json:
        return ""
    cols = schema_json.get("columns", [])
    lines = [f"Dataset columns ({len(cols)} total):"]
    for c in cols[:30]:  # cap at 30 columns to keep context short
        lines.append(
            f"  - {c.get('name', '?')} ({c.get('semantic_type', c.get('data_type', 'unknown'))})"
            + (
                f" [{c.get('null_rate', 0.0) * 100:.0f}% null]"
                if c.get("null_rate", 0) > 0.01
                else ""
            )
        )
    return "\n".join(lines)
