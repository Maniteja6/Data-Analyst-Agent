"""Report generation LangGraph graph — produces PDF/XLSX/PPTX from an InsightReport.

This is a simpler, linear graph compared to the analysis pipeline.
It is invoked by the ``generate_report`` Celery task after the full
analysis is complete and the user requests an export.

Graph topology
--------------
  START → load_report_node → render_node → upload_node → END

Usage::

    graph  = build_report_generation_graph()
    result = await graph.ainvoke({
        "context": {
            "dataset_id":  "abc-123",
            "session_id":  "def-456",
            "format":      "pdf",
            "report_id":   None,
        }
    })
    download_url = result["context"]["download_url"]
"""
from __future__ import annotations

from langgraph.graph import StateGraph, END
from backend.orchestration.state.pipeline_state import PipelineState
import structlog

logger = structlog.get_logger(__name__)


async def load_report_node(state: PipelineState) -> dict:
    """Load the InsightReport from cache or Postgres."""
    ctx = state.get("context", {})
    try:
        from backend.infrastructure.cache.redis_cache_adapter import get_redis_cache
        cache  = get_redis_cache()
        cached = await cache.get_json(f"insights:{ctx.get('dataset_id', '')}")
        if cached:
            return {"final_report": cached}

        from backend.infrastructure.persistence.database import get_session
        from backend.infrastructure.persistence.repositories.postgres_insight_repository import (
            PostgresInsightRepository,
        )
        async with get_session() as db_session:
            repo   = PostgresInsightRepository(db_session)
            report = await repo.get_by_dataset_id(ctx.get("dataset_id", ""))
            if report:
                return {"final_report": report.to_dict()}
        return {"final_report": {}, "errors": ["No insight report found for dataset."]}
    except Exception as exc:
        return {"final_report": {}, "errors": [f"LoadReportNode: {exc}"]}


async def render_node(state: PipelineState) -> dict:
    """Render the report to the requested format (PDF/XLSX/PPTX/JSON)."""
    ctx    = state.get("context", {})
    report = state.get("final_report", {})
    fmt    = ctx.get("format", "json")
    if not report:
        return {"errors": ["render_node: no report data available"]}

    try:
        from backend.infrastructure.job_queue.tasks.report_tasks import (
            _render_report,
            _content_type,
        )
        rendered_bytes = await _render_report(report, fmt)
        return {"context": {**ctx, "rendered_bytes": rendered_bytes, "content_type": _content_type(fmt)}}
    except Exception as exc:
        return {"errors": [f"RenderNode: {exc}"]}


async def upload_node(state: PipelineState) -> dict:
    """Upload the rendered bytes to S3 and generate a presigned URL."""
    ctx = state.get("context", {})
    rendered_bytes = ctx.get("rendered_bytes")
    if not rendered_bytes:
        return {"errors": ["upload_node: no rendered bytes"]}

    try:
        import io
        from backend.infrastructure.storage.s3_storage_adapter import get_s3_storage
        from backend.shared.utils.uuid_factory import new_uuid

        storage     = get_s3_storage()
        export_id   = new_uuid()
        fmt         = ctx.get("format", "json")
        storage_key = f"reports/{ctx.get('dataset_id', 'unknown')}/{export_id}.{fmt}"

        await storage.upload_fileobj(io.BytesIO(rendered_bytes), storage_key, ctx.get("content_type"))
        url = await storage.generate_presigned_download_url(storage_key)

        logger.info("report_uploaded", key=storage_key, format=fmt)
        return {"context": {**ctx, "storage_key": storage_key, "download_url": url}}
    except Exception as exc:
        return {"errors": [f"UploadNode: {exc}"]}


def build_report_generation_graph() -> StateGraph:
    """Build and compile the report generation StateGraph."""
    graph = StateGraph(PipelineState)

    graph.add_node("load",   load_report_node)
    graph.add_node("render", render_node)
    graph.add_node("upload", upload_node)

    graph.set_entry_point("load")
    graph.add_edge("load",   "render")
    graph.add_edge("render", "upload")
    graph.add_edge("upload", END)

    return graph.compile()
