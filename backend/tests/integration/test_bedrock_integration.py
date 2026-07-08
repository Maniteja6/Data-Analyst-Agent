"""Bedrock integration tests — skipped unless real AWS credentials are present."""

import os

import pytest

SKIP_REASON = "Requires real AWS credentials and FEATURE_BEDROCK=true env var"
REQUIRES_BEDROCK = pytest.mark.skipif(
    os.environ.get("FEATURE_BEDROCK") != "true",
    reason=SKIP_REASON,
)


@pytest.mark.integration
@pytest.mark.bedrock
class TestBedrockConverseAdapter:
    @REQUIRES_BEDROCK
    @pytest.mark.asyncio
    async def test_complete_returns_non_empty_string(self) -> None:
        from backend.infrastructure.llm.bedrock.bedrock_converse_adapter import (
            BedrockConverseAdapter,
        )

        adapter = BedrockConverseAdapter()
        result = await adapter.complete(
            prompt="Return the number 42. Only the number.",
            max_tokens=10,
        )
        assert "42" in result

    @REQUIRES_BEDROCK
    @pytest.mark.asyncio
    async def test_complete_with_json_format(self) -> None:
        from backend.infrastructure.llm.bedrock.bedrock_converse_adapter import (
            BedrockConverseAdapter,
        )

        adapter = BedrockConverseAdapter()
        result = await adapter.complete(
            prompt='Return {"answer": 42} as JSON.',
            response_format=dict,
        )
        import json

        data = json.loads(result)
        assert "answer" in data


@pytest.mark.integration
@pytest.mark.bedrock
class TestBedrockEmbeddingAdapter:
    @REQUIRES_BEDROCK
    @pytest.mark.asyncio
    async def test_embed_returns_1536_dim_vector(self) -> None:
        from backend.infrastructure.llm.bedrock.bedrock_embedding_adapter import (
            BedrockEmbeddingAdapter,
        )

        adapter = BedrockEmbeddingAdapter()
        vector = await adapter.embed("Sample text for embedding test.")
        assert len(vector) == 1536
        assert all(isinstance(v, float) for v in vector)
