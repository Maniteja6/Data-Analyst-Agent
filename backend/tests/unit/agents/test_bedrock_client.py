"""Unit tests for Bedrock client and retry handler."""

from typing import Never
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.unit
class TestBedrockRetryHandler:
    @pytest.mark.asyncio
    async def test_passes_through_on_success(self) -> None:
        from backend.infrastructure.llm.bedrock.bedrock_retry_handler import with_bedrock_retry

        call_count = 0

        @with_bedrock_retry
        async def my_fn() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await my_fn()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_throttling_then_succeeds(self) -> None:
        from backend.infrastructure.llm.bedrock.bedrock_retry_handler import with_bedrock_retry
        from botocore.exceptions import ClientError

        call_count = 0

        @with_bedrock_retry(max_retries=3)
        async def flaky_fn() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ClientError(
                    {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
                    "Converse",
                )
            return "success"

        with patch("asyncio.sleep", AsyncMock()):
            result = await flaky_fn()

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_non_retryable_error_propagates_immediately(self) -> None:
        from backend.infrastructure.llm.bedrock.bedrock_retry_handler import with_bedrock_retry
        from botocore.exceptions import ClientError

        call_count = 0

        @with_bedrock_retry(max_retries=3)
        async def always_403() -> Never:
            nonlocal call_count
            call_count += 1
            raise ClientError(
                {"Error": {"Code": "AccessDeniedException", "Message": "No access"}},
                "Converse",
            )

        with pytest.raises(ClientError):
            await always_403()
        assert call_count == 1  # no retry on AccessDenied


@pytest.mark.unit
class TestLLMResponseParsing:
    def test_as_json_strips_markdown_fences(self) -> None:
        from backend.domain.intelligence.value_objects.llm_response import LLMResponse

        resp = LLMResponse(content='```json\n{"key": "value"}\n```')
        data = resp.as_json()
        assert data == {"key": "value"}

    def test_as_json_safe_returns_default_on_invalid(self) -> None:
        from backend.domain.intelligence.value_objects.llm_response import LLMResponse

        resp = LLMResponse(content="not valid json at all")
        data = resp.as_json_safe(default={"fallback": True})
        assert data == {"fallback": True}

    def test_as_sql_strips_code_fence(self) -> None:
        from backend.domain.intelligence.value_objects.llm_response import LLMResponse

        resp = LLMResponse(content="```sql\nSELECT COUNT(*) FROM df\n```")
        sql = resp.as_sql()
        assert sql == "SELECT COUNT(*) FROM df"

    def test_was_truncated_on_max_tokens(self) -> None:
        from backend.domain.intelligence.value_objects.llm_response import LLMResponse

        resp = LLMResponse(content="partial", stop_reason="max_tokens")
        assert resp.was_truncated is True

    def test_cost_estimate_calculation(self) -> None:
        from backend.domain.intelligence.value_objects.llm_response import LLMResponse

        resp = LLMResponse(
            content="test",
            model_id="anthropic.claude-sonnet-4-5",
            input_tokens=1_000_000,
            output_tokens=0,
        )
        assert resp.estimated_cost_usd == pytest.approx(3.0, abs=0.01)
