"""AgentContext — shared mutable state flowing through the pipeline DAG.

Designed for real-time applications: all fields are mutable so nodes and
agents can update state in place without copying. The context object is
created once per analysis session and passed through every agent in the DAG.

Thread safety:
    AgentContext is NOT thread-safe. Parallel agents in the DAG should
    write to different fields (sql_results vs forecast_results) and let
    the ResultAggregator merge after all tasks complete.

WebSocket integration:
    ``push_progress(sio, progress, message)`` emits a ``job:progress``
    Socket.IO event to the dataset's room so the browser updates in real-time
    without polling.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class AgentContext:
    """Shared mutable state for one analysis pipeline run.

    Core identity fields (required at construction):
        session_id:      AnalysisSession UUID
        dataset_id:      Dataset UUID
        correlation_id:  Request-scoped tracing ID
        storage_key:     S3 key or local path to the dataset file

    Stage outputs (populated by agents as the pipeline progresses):
        schema:          Column schema from SchemaAgent
        profile:         DataProfile dict from ProfilingAgent
        cleaning_report: CleaningReport dict from DataCleaner
        sql_results:     List of SQL query result dicts from SQLAgent
        python_results:  List of analysis result dicts from PythonAgent
        forecast_results: List of forecast dicts from ForecastAgent
        ml_results:      ML model result dict from MLAgent
        anomaly_results: Anomaly dicts from AnomalyDetector
        visualization_specs: Vega-Lite spec dicts from VisualizationAgent
        insight_results: Insight dicts from InsightAgent
        rag_context:     Retrieved RAG chunk text for the current query
        conversation_history: Full Bedrock Converse API message list

    Runtime:
        metadata:        Free-form dict for cross-agent communication
        _sio:            Socket.IO server reference for real-time progress pushes
    """

    # ── Identity (required) ───────────────────────────────────────────────
    session_id: str
    dataset_id: str
    correlation_id: str
    storage_key: str

    # ── Pipeline stage outputs (populated by agents) ──────────────────────
    schema: dict | None = None
    profile: dict | None = None
    cleaning_report: dict | None = None
    sql_results: list[dict] = field(default_factory=list)
    python_results: list[dict] = field(default_factory=list)
    forecast_results: list[dict] = field(default_factory=list)
    ml_results: dict | None = None
    anomaly_results: list[dict] = field(default_factory=list)
    visualization_specs: list[dict] = field(default_factory=list)
    insight_results: list[dict] = field(default_factory=list)
    recommendations: list[dict] = field(default_factory=list)
    rag_context: str | None = None
    conversation_history: list[dict] = field(default_factory=list)

    # ── Runtime ───────────────────────────────────────────────────────────
    metadata: dict[str, Any] = field(default_factory=dict)
    _sio: Any = field(default=None, repr=False)  # Socket.IO server

    # ── Convenience accessors ─────────────────────────────────────────────

    def set(self, key: str, value: Any) -> None:  # noqa: ANN401
        """Store a value in the free-form metadata dict."""
        self.metadata[key] = value

    def get(self, key: str, default: Any = None) -> Any:  # noqa: ANN401
        """Retrieve a value from the metadata dict."""
        return self.metadata.get(key, default)

    @property
    def has_schema(self) -> bool:
        return self.schema is not None and bool(self.schema.get("columns"))

    @property
    def has_profile(self) -> bool:
        return self.profile is not None

    @property
    def has_time_series(self) -> bool:
        if not self.schema:
            return False
        return any(
            c.get("semantic_type") in ("date", "datetime") for c in self.schema.get("columns", [])
        )

    @property
    def numeric_column_count(self) -> int:
        if not self.schema:
            return 0
        numeric = {"currency", "numeric_measure", "numeric_count", "percentage"}
        return sum(1 for c in self.schema.get("columns", []) if c.get("semantic_type") in numeric)

    @property
    def column_names(self) -> list[str]:
        if not self.schema:
            return []
        return [c["name"] for c in self.schema.get("columns", [])]

    # ── Real-time Socket.IO progress push ─────────────────────────────────

    async def push_progress(
        self,
        progress: int,
        message: str,
        step: str = "",
        extra: dict | None = None,
    ) -> None:
        """Emit a job:progress event to the dataset's Socket.IO room.

        Args:
            progress: Integer 0–100 representing pipeline completion.
            message:  Human-readable status message for the UI.
            step:     Current pipeline step name (e.g. 'profiling', 'insight').
            extra:    Optional dict of additional fields to include in the event.
        """
        if self._sio is None:
            return
        try:
            payload = {
                "type": "job.progress",
                "dataset_id": self.dataset_id,
                "session_id": self.session_id,
                "correlation_id": self.correlation_id,
                "progress": progress,
                "message": message,
                "step": step,
                "timestamp": datetime.now(UTC).isoformat(),
                **(extra or {}),
            }
            await self._sio.emit(
                "job:progress",
                payload,
                room=f"dataset:{self.dataset_id}",
            )
        except Exception as exc:
            logger.debug("push_progress_emit_failed", error=str(exc))

    async def push_token(self, token: str, message_id: str = "") -> None:
        """Emit a single LLM token to the conversation's Socket.IO room.

        Used by streaming chat agents to push tokens one-by-one to the browser.

        Args:
            token:      Single token or small chunk of text.
            message_id: Assistant message UUID (for multi-message ordering).
        """
        if self._sio is None:
            return
        conversation_id = self.get("conversation_id", "")
        if not conversation_id:
            return
        with contextlib.suppress(Exception):
            await self._sio.emit(
                "chat:token",
                {"token": token, "message_id": message_id},
                room=f"conversation:{conversation_id}",
            )

    async def push_complete(self, payload: dict) -> None:
        """Emit a chat:complete event when the full response is ready.

        Args:
            payload: Final response dict with content, citations, visualizations.
        """
        if self._sio is None:
            return
        conversation_id = self.get("conversation_id", "")
        if not conversation_id:
            return
        with contextlib.suppress(Exception):
            await self._sio.emit(
                "chat:complete",
                payload,
                room=f"conversation:{conversation_id}",
            )

    # ── Serialisation ─────────────────────────────────────────────────────

    def summary_dict(self) -> dict:
        """Return a lightweight summary of the context state for logging."""
        return {
            "session_id": self.session_id,
            "dataset_id": self.dataset_id,
            "correlation_id": self.correlation_id,
            "has_schema": self.has_schema,
            "has_profile": self.has_profile,
            "has_time_series": self.has_time_series,
            "sql_results_count": len(self.sql_results),
            "anomaly_count": len(self.anomaly_results),
            "insight_count": len(self.insight_results),
            "numeric_col_count": self.numeric_column_count,
        }
