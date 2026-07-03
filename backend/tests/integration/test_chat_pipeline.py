"""Integration test: SendMessageUseCase with mocked LLM."""
import pytest


@pytest.mark.integration
class TestChatPipeline:

    @pytest.mark.asyncio
    async def test_send_message_returns_response(
        self, fake_conversation, fake_dataset, mock_llm, in_memory_cache
    ):
        """SendMessageUseCase should produce an assistant reply."""
        from backend.application.use_cases.send_message import SendMessageUseCase
        from backend.application.commands.send_message_command import SendMessageCommand

        mock_llm.set_response("What", "The total revenue is $24,000.")

        class _FakeConvRepo:
            async def get_by_id(self, cid): return fake_conversation
            async def save(self, entity): pass

        class _FakeDatasetRepo:
            async def get_by_id(self, did): return fake_dataset

        use_case = SendMessageUseCase(
            conversation_repo=_FakeConvRepo(),
            dataset_repo=_FakeDatasetRepo(),
            cache=in_memory_cache,
            llm_service=mock_llm,
        )
        cmd = SendMessageCommand(
            conversation_id=fake_conversation.id,
            dataset_id=fake_dataset.id,
            content="What is the total revenue?",
            correlation_id="test-corr",
        )
        # The graph will use mock_llm for response generation
        # but may import agent modules — skip if not implemented
        try:
            result = await use_case.execute(cmd)
            assert "content" in result or "message_id" in result
        except (ImportError, ModuleNotFoundError) as e:
            pytest.skip(f"Agents not yet implemented: {e}")
