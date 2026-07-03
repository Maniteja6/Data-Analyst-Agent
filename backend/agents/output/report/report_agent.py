"""ReportAgent — orchestrates multi-format report generation with real-time events.

Real-time pipeline:
    The ReportAgent is the final agent in the DAG. It:
    1. Receives the complete InsightReport (post-critique, post-recommendation)
    2. Renders the requested format (PDF/XLSX/PPTX/JSON) in a thread pool
    3. Uploads the rendered bytes to S3
    4. Generates a presigned download URL (valid 15 minutes)
    5. Emits ``report:ready`` with the download URL to the dataset's Socket.IO room
    6. Caches the download URL in Redis so the job poller can return it

Socket.IO events emitted:
    report:render_start  — "Generating PDF…"
    report:page_complete — per page/slide/sheet during render (forwarded from sub-generators)
    report:uploading     — "Uploading to secure storage…"
    report:ready         — {download_url, format, expires_in} — triggers frontend download
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from backend.agents.base.base_agent import BaseAgent
from backend.agents.base.agent_context import AgentContext
from backend.agents.output.report.excel_exporter import export_to_excel
from backend.agents.output.report.pdf_generator   import export_to_pdf
from backend.agents.output.report.pptx_generator  import export_to_pptx
from backend.shared.utils.uuid_factory import new_uuid

logger = structlog.get_logger(__name__)

PRESIGNED_URL_TTL = 900   # 15 minutes


class ReportAgent(BaseAgent):
    """Renders and uploads the final InsightReport in multiple formats.

    Args:
        storage:     IStorageService for S3 uploads.
        llm_client:  Optional LLM client (not used in rendering but kept for
                     interface consistency with other agents).
    """

    def __init__(self, storage=None, llm_client=None) -> None:
        super().__init__("report")
        self._storage = storage

    async def _execute(
        self,
        context: AgentContext,
        format: str = "json",
        insight_report: dict | None = None,
        **kwargs: Any,
    ) -> dict:
        """Render the report and upload to S3.

        Args:
            context:        Shared pipeline state.
            format:         Output format: ``pdf`` | ``xlsx`` | ``pptx`` | ``json``.
            insight_report: InsightReport dict. Falls back to context.insight_results.

        Returns:
            Dict with keys: format, download_url, storage_key, expires_in, bytes_written.
        """
        sio        = context._sio
        dataset_id = context.dataset_id
        fmt        = format.lower()

        # Build full report dict
        report = insight_report or {
            "session_id":        context.session_id,
            "dataset_id":        dataset_id,
            "executive_summary": "",
            "insights":          context.insight_results or [],
            "kpis":              [],
            "anomaly_alerts":    context.anomaly_results or [],
            "forecasts":         context.forecast_results or [],
            "recommendations":   context.recommendations or [],
            "has_forecasts":     bool(context.forecast_results),
            "has_anomalies":     bool(context.anomaly_results),
            "insight_count":     len(context.insight_results or []),
        }

        dataset_name = context.get("dataset_name", f"Dataset {dataset_id[:8]}")

        # ── Notify render start ───────────────────────────────────────────
        if sio and dataset_id:
            try:
                await sio.emit(
                    "report:render_start",
                    {"dataset_id": dataset_id, "format": fmt},
                    room=f"dataset:{dataset_id}",
                )
            except Exception:
                pass

        await context.push_progress(96, f"Generating {fmt.upper()} report…", step="report")

        # ── Render ────────────────────────────────────────────────────────
        rendered_bytes = await self._render(report, fmt, dataset_name, sio, dataset_id)

        if not rendered_bytes:
            return {
                "format": fmt,
                "error":  f"Failed to render {fmt} report",
                "download_url": None,
            }

        # ── Upload to S3 ──────────────────────────────────────────────────
        if sio and dataset_id:
            try:
                await sio.emit(
                    "report:uploading",
                    {"dataset_id": dataset_id, "format": fmt},
                    room=f"dataset:{dataset_id}",
                )
            except Exception:
                pass

        export_id   = new_uuid()
        storage_key = f"reports/{dataset_id}/{export_id}.{fmt}"
        mime_type   = self._content_type(fmt)

        download_url = None
        try:
            storage = self._get_storage()
            import io
            await storage.upload_fileobj(
                io.BytesIO(rendered_bytes),
                storage_key,
                content_type=mime_type,
            )
            download_url = await storage.generate_presigned_download_url(
                storage_key, ttl=PRESIGNED_URL_TTL
            )
        except Exception as exc:
            logger.warning("report_upload_failed", error=str(exc))

        # ── Cache the download URL for job polling ────────────────────────
        if download_url:
            try:
                from backend.infrastructure.cache.redis_cache_adapter import get_redis_cache
                await get_redis_cache().set(
                    f"report_url:{export_id}",
                    download_url,
                    ttl=PRESIGNED_URL_TTL,
                )
            except Exception:
                pass

        result = {
            "format":       fmt,
            "export_id":    export_id,
            "storage_key":  storage_key,
            "download_url": download_url,
            "expires_in":   PRESIGNED_URL_TTL,
            "bytes_written": len(rendered_bytes),
        }

        # ── Emit report:ready ─────────────────────────────────────────────
        if sio and dataset_id:
            try:
                await sio.emit(
                    "report:ready",
                    {
                        "dataset_id":   dataset_id,
                        "format":       fmt,
                        "download_url": download_url,
                        "expires_in":   PRESIGNED_URL_TTL,
                        "export_id":    export_id,
                    },
                    room=f"dataset:{dataset_id}",
                )
            except Exception:
                pass

        await context.push_progress(100, "Report ready", step="report")

        logger.info(
            "report_agent_complete",
            format=fmt,
            bytes=len(rendered_bytes),
            has_url=bool(download_url),
        )
        return result

    # ── Render dispatch ───────────────────────────────────────────────────

    async def _render(
        self, report: dict, fmt: str, dataset_name: str, sio, dataset_id: str
    ) -> bytes | None:
        try:
            if fmt == "pdf":
                return await export_to_pdf(report, dataset_name, sio, dataset_id)
            if fmt == "xlsx":
                return await export_to_excel(report, sio, dataset_id)
            if fmt == "pptx":
                return await export_to_pptx(report, dataset_name, sio, dataset_id)
            if fmt == "json":
                return json.dumps(report, default=str, indent=2).encode("utf-8")
        except Exception as exc:
            logger.error("report_render_failed", format=fmt, error=str(exc))
        return None

    @staticmethod
    def _content_type(fmt: str) -> str:
        return {
            "pdf":  "application/pdf",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "json": "application/json",
        }.get(fmt, "application/octet-stream")

    def _get_storage(self):
        if self._storage is None:
            from backend.infrastructure.storage.s3_storage_adapter import get_s3_storage
            self._storage = get_s3_storage()
        return self._storage
