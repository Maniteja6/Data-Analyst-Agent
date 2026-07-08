"""ProfilingNode — runs DataProfiler and stores the DataProfile in state."""

from __future__ import annotations

import structlog
from backend.orchestration.state.pipeline_state import PipelineState

logger = structlog.get_logger(__name__)


async def profiling_node(state: PipelineState) -> dict:
    """LangGraph node: profile all columns in the dataset.

    Reads:  state['context'], state['schema_result']
    Writes: state['profile_result'] — DataProfile.to_dict()
    """
    ctx = state.get("context", {})
    try:
        from backend.analytics_engine.ingestion.file_reader import FileReader
        from backend.analytics_engine.profiling.data_profiler import DataProfiler

        reader = FileReader()
        df = await reader.read(ctx["storage_key"])
        profiler = DataProfiler()
        profile = await profiler.profile(
            df,
            session_id=ctx.get("session_id", ""),
            dataset_id=ctx.get("dataset_id", ""),
        )

        logger.info(
            "profiling_node_complete",
            rows=profile.row_count,
            cols=profile.column_count,
            completeness=profile.completeness_score,
        )
        return {"profile_result": profile.to_dict()}

    except Exception as exc:
        logger.error("profiling_node_failed", error=str(exc))
        return {"profile_result": {}, "errors": [f"ProfilingNode: {exc}"]}
