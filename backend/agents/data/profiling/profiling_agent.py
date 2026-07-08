"""ProfilingAgent — runs DataProfiler with real-time column-by-column Socket.IO events.

Real-time design:
    For a 50-column dataset, full profiling can take 3-5 seconds. Rather
    than emitting one event at the end, the ProfilingAgent emits a
    ``profiling:column_complete`` event after each column is profiled so
    the frontend can render a live-updating profile table.

    The profiling loop runs in a thread pool executor so the asyncio event
    loop is never blocked. The emit_progress callback bridges the sync
    DataProfiler loop back to the async Socket.IO server via
    ``asyncio.run_coroutine_threadsafe``.

Socket.IO events emitted:
    profiling:start          — "Profiling N columns…"
    profiling:column_complete — per-column stats as they complete
    profiling:complete        — full DataProfile dict on completion
"""

from __future__ import annotations

import asyncio
import contextlib
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import structlog
from backend.agents.base.agent_context import AgentContext
from backend.agents.base.base_agent import BaseAgent
from backend.analytics_engine.profiling.data_profiler import DataProfiler

logger = structlog.get_logger(__name__)

# Shared executor for profiling (CPU-bound)
_PROFILING_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="profiling_worker")


class ProfilingAgent(BaseAgent):
    """Integrates DataProfiler into the agent DAG with real-time column events."""

    def __init__(self) -> None:
        super().__init__("profiling")
        self._profiler = DataProfiler()

    async def _execute(self, context: AgentContext, **kwargs: Any) -> dict:  # noqa: ANN401
        """Profile all columns and emit per-column Socket.IO events.

        Returns:
            DataProfile serialised as a dict (profile.to_dict() output).
        """
        sio = context._sio
        dataset_id = context.dataset_id

        # Load the full dataset (not sample — profiling needs all rows)
        from backend.analytics_engine.ingestion.file_reader import FileReader

        await context.push_progress(19, "Loading dataset for profiling…", step="profiling")
        df = await FileReader().read(context.storage_key)

        col_count = len(df.columns) if hasattr(df, "columns") else df.shape[1]

        if sio and dataset_id:
            with contextlib.suppress(Exception):
                await sio.emit(
                    "profiling:start",
                    {"dataset_id": dataset_id, "column_count": col_count},
                    room=f"dataset:{dataset_id}",
                )

        await context.push_progress(21, f"Profiling {col_count} columns…", step="profiling")

        # Build a progress callback that bridges sync → async Socket.IO
        loop = asyncio.get_event_loop()
        columns_done = [0]

        def column_done_callback(col_name: str, col_profile: Any) -> None:  # noqa: ANN401
            """Called from the profiling thread after each column completes."""
            columns_done[0] += 1
            progress = 21 + int((columns_done[0] / col_count) * 10)  # 21% → 31%

            if sio and dataset_id:
                try:
                    col_dict = col_profile.to_dict() if hasattr(col_profile, "to_dict") else {}
                    asyncio.run_coroutine_threadsafe(
                        sio.emit(
                            "profiling:column_complete",
                            {
                                "dataset_id": dataset_id,
                                "column_name": col_name,
                                "column_index": columns_done[0],
                                "total": col_count,
                                "progress": progress,
                                "profile": col_dict,
                            },
                            room=f"dataset:{dataset_id}",
                        ),
                        loop,
                    )
                except Exception as exc:
                    logger.debug("profiling_progress_emit_failed", error=str(exc))

        # Run profiling in thread pool with the callback
        profile = await loop.run_in_executor(
            _PROFILING_POOL,
            lambda: self._profiler._profile_sync_with_callback(
                df,
                session_id=context.session_id,
                dataset_id=context.dataset_id,
                column_callback=column_done_callback,
            ),
        )

        profile_dict = profile.to_dict() if hasattr(profile, "to_dict") else profile
        context.profile = profile_dict

        # Emit profiling:complete
        if sio and dataset_id:
            with contextlib.suppress(Exception):
                await sio.emit(
                    "profiling:complete",
                    {
                        "dataset_id": dataset_id,
                        "row_count": profile_dict.get("row_count", 0),
                        "column_count": profile_dict.get("column_count", 0),
                        "completeness_score": profile_dict.get("completeness_score", 0),
                        "duplicate_count": profile_dict.get("duplicate_count", 0),
                    },
                    room=f"dataset:{dataset_id}",
                )

        logger.info(
            "profiling_agent_complete",
            rows=profile_dict.get("row_count", 0),
            cols=profile_dict.get("column_count", 0),
            completeness=profile_dict.get("completeness_score", 0),
        )
        return profile_dict
