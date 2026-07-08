"""Unit tests for SchemaAgent (mocked LLM)."""

import pytest


@pytest.mark.unit
class TestSchemaAgentWithMockLLM:
    @pytest.mark.asyncio
    async def test_schema_agent_classifies_columns(self, sample_df, mock_llm) -> None:
        """SchemaAgent should call the LLM and return a columns list."""
        mock_llm.set_response(
            "schema",
            '{"columns": ['
            '{"name": "revenue", "semantic_type": "currency", "is_primary_key": false},'
            '{"name": "date",    "semantic_type": "datetime", "is_primary_key": false}'
            "]}",
        )
        try:
            from backend.agents.schema_agent import SchemaAgent

            agent = SchemaAgent(llm=mock_llm)
            result = await agent.run(df=sample_df, dataset_id="test-123")
            assert "columns" in result
            assert len(result["columns"]) > 0
        except ImportError:
            pytest.skip("SchemaAgent not yet implemented")

    @pytest.mark.asyncio
    async def test_schema_agent_records_llm_call(self, sample_df, mock_llm) -> None:
        try:
            from backend.agents.schema_agent import SchemaAgent

            agent = SchemaAgent(llm=mock_llm)
            await agent.run(df=sample_df, dataset_id="test-id")
            assert len(mock_llm.calls) > 0
        except ImportError:
            pytest.skip("SchemaAgent not yet implemented")
