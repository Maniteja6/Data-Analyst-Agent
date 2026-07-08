"""SchemaNode — calls the SchemaAgent to infer column semantic types."""

from __future__ import annotations

import structlog
from backend.orchestration.state.pipeline_state import PipelineState

logger = structlog.get_logger(__name__)


async def schema_node(state: PipelineState) -> dict:
    """LangGraph node: run schema inference on the uploaded dataset.

    Reads:  state['context'] — {dataset_id, storage_key, session_id}
    Writes: state['schema_result'] — ColumnSchema list dict

    On failure, appends an error and returns an empty schema_result
    so downstream nodes can proceed with unknown semantic types.
    """
    ctx = state.get("context", {})
    try:
        from backend.agents.schema_agent import SchemaAgent
        from backend.analytics_engine.ingestion.file_reader import FileReader
        from backend.infrastructure.llm.bedrock.bedrock_converse_adapter import (
            BedrockConverseAdapter,
        )

        reader = FileReader()
        df = await reader.read(ctx["storage_key"], sample_rows=500)

        agent = SchemaAgent(llm=BedrockConverseAdapter())
        result = await agent.run(df=df, dataset_id=ctx.get("dataset_id", ""))

        logger.info("schema_node_complete", columns=len(result.get("columns", [])))
        return {"schema_result": result}

    except Exception as exc:
        logger.error("schema_node_failed", error=str(exc))
        return {"schema_result": {}, "errors": [f"SchemaNode: {exc}"]}
