"""CleaningNode — runs DataCleaner and stores the CleaningReport in state."""

from __future__ import annotations

import structlog
from backend.orchestration.state.pipeline_state import PipelineState

logger = structlog.get_logger(__name__)


async def cleaning_node(state: PipelineState) -> dict:
    """LangGraph node: clean the dataset and write the CleaningReport.

    Reads:  state['context'], state['profile_result']
    Writes: state['cleaning_result'] — {cleaning_report: dict, rows_after: int}
    """
    ctx = state.get("context", {})
    profile = state.get("profile_result", {})
    try:
        from backend.analytics_engine.cleaning.data_cleaner import DataCleaner
        from backend.analytics_engine.ingestion.file_reader import FileReader

        reader = FileReader()
        df = await reader.read(ctx["storage_key"])

        # Build a lightweight profile proxy for the cleaner
        class _ProfileProxy:
            column_profiles = [
                type(
                    "CP",
                    (),
                    {
                        "column_name": c.get("column_name", ""),
                        "null_rate": c.get("null_rate", 0.0),
                        "kind": type("K", (), {"value": c.get("kind", "unknown")})(),
                        "semantic_type": type(
                            "ST", (), {"value": c.get("semantic_type", "unknown")}
                        )(),
                        "data_type": c.get("data_type", "unknown"),
                    },
                )()
                for c in profile.get("column_profiles", [])
            ]

        cleaner = DataCleaner()
        _, report = await cleaner.clean(
            df,
            _ProfileProxy(),
            session_id=ctx.get("session_id", ""),
            dataset_id=ctx.get("dataset_id", ""),
        )

        logger.info(
            "cleaning_node_complete",
            rows_removed=report.rows_removed,
            steps=len(report.steps),
        )
        return {
            "cleaning_result": {
                "cleaning_report": report.to_dict(),
                "rows_after": report.rows_after,
                "columns_after": report.columns_after,
            }
        }
    except Exception as exc:
        logger.error("cleaning_node_failed", error=str(exc))
        return {"cleaning_result": {}, "errors": [f"CleaningNode: {exc}"]}
