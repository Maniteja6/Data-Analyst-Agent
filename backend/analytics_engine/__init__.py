"""Analytics engine — deterministic, streaming-ready data processing pipeline.

Designed for real-time applications where users see results column-by-column
as they arrive rather than waiting for the full pipeline to complete.

Sub-packages
------------
ingestion/
    FileReader      — async read() from S3 or local path → polars/pandas DataFrame
    FormatDetector  — magic-byte + extension + csv.Sniffer; returns FileFormatInfo
    StreamProcessor — async generators for CSV/Parquet > max_rows_in_memory

profiling/
    DataProfiler    — orchestrates per-column profilers; emits column_callback
                      per column so Socket.IO events fire as each column finishes
    NumericProfiler — StatisticalSummary (mean/stddev/P5-P95/skew/kurt) + Histogram
    CategoricalProfiler — top-N value_counts + categorical Histogram
    DatetimeProfiler    — min/max date, inferred frequency, gap detection
    TextProfiler        — length stats, whitespace detection, sample values

cleaning/
    DataCleaner         — orchestrator: whitespace → dedup → coerce → impute → clip
    DuplicateRemover    — polars unique() / pandas drop_duplicates()
    MissingValueHandler — drop cols ≥ 80% null; impute numeric=median, text=mode
    TypeCoercer         — string → float (strips $€£%) and string → datetime
    OutlierHandler      — optional Tukey fence clipping (disabled by default)

anomaly_detection/
    AnomalyDetector     — orchestrator: per-column + multivariate; dedup + rank
    ZScoreDetector      — |z| ≥ threshold; polars-first, pandas fallback
    IQRDetector         — Tukey fence; multiplier configurable (1.5 / 3.0)
    IsolationForestDetector — sklearn multivariate; samples to 10% above 50k rows
    RuleDetector        — semantic rules: negative currency, % range, date bounds

sql_engine/
    DuckDBManager   — async context manager; registers DataFrame as DuckDB view;
                      separate thread pool from S3 and embedding pools
    QueryBuilder    — builds safe SELECT-only DuckDB queries from intent dicts;
                      double-quotes all identifiers; blocks 15 DDL/DML keywords
    ResultFormatter — to_markdown_table(), to_vega_data(), summarise(), to_json()

statistics/
    CorrelationEngine   — pairwise Pearson r; filters |r| ≥ min_abs_r; polars-first
    TrendAnalyzer       — linear trend via np.polyfit(date.toordinal(), y, 1);
                          returns slope, R², direction, pct_change, is_significant
    HypothesisTester    — Welch t-test and chi-square independence test
    DistributionFitter  — tests norm/expon/lognorm/gamma/beta via scipy kstest

Real-time streaming API
-----------------------
Every primary class is synchronous (CPU-bound numpy/polars) and runs in a
ThreadPoolExecutor so the asyncio event loop is never blocked.  The async
wrappers below are the recommended entry points for real-time applications:

    # Stream per-column profiling events to Socket.IO
    async def handle_analysis(storage_key, sio, dataset_id):
        from backend.analytics_engine import profile_with_events

        profile = await profile_with_events(
            storage_key=storage_key,
            sio=sio,
            dataset_id=dataset_id,
        )
        # Each column fires "profiling:column_complete" as it finishes —
        # the browser renders cards one-by-one without waiting for all columns.

    # Run the full deterministic pipeline in one call
    from backend.analytics_engine import run_pipeline

    result = await run_pipeline(
        storage_key="datasets/abc/sales.csv",
        session_id="s1",
        dataset_id="d1",
        sio=sio,               # pass None for batch/Celery mode
    )
    # result.df         — cleaned DataFrame
    # result.profile    — DataProfile entity
    # result.report     — CleaningReport entity
    # result.anomalies  — list[dict] sorted by severity

Socket.IO events emitted (dataset:<dataset_id> room)
-----------------------------------------------------
profiling:start              {"column_count": N}
profiling:column_complete    {"column_name", "column_index", "total", "profile"}
profiling:complete           {"row_count", "column_count", "completeness_score"}
cleaning:start               {"steps": [...]}
cleaning:complete            {"rows_removed", "columns_removed"}
anomaly:start                {}
anomaly:detected             {"column", "severity", "description"}  (per anomaly)
anomaly:complete             {"total_count"}
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd
    import polars as pl
    from backend.domain.analytics.entities.data_profile import DataProfile

# ---------------------------------------------------------------------------
# Convenience result container
# ---------------------------------------------------------------------------


@dataclass
class PipelineResult:
    """Holds all outputs of the deterministic analytics pipeline."""

    df: Any = None  # cleaned polars/pandas DataFrame
    profile: Any = None  # DataProfile entity
    report: Any = None  # CleaningReport entity
    anomalies: list[dict] = field(default_factory=list)
    schema: dict = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# High-level async entry points for real-time applications
# ---------------------------------------------------------------------------


async def run_pipeline(
    storage_key: str,
    session_id: str = "",
    dataset_id: str = "",
    sio: Any = None,  # noqa: ANN401
    run_anomaly: bool = True,
    sample_rows: int | None = None,
) -> PipelineResult:
    """Run the full deterministic pipeline: ingest → profile → clean → anomaly.

    This is the single recommended entry point for Celery tasks and LangGraph
    nodes. All steps run sequentially; each emits Socket.IO progress events
    when ``sio`` is provided.

    Args:
        storage_key:  S3 key or local path to the dataset file.
        session_id:   AnalysisSession UUID (included in events).
        dataset_id:   Dataset UUID (used as Socket.IO room suffix).
        sio:          Socket.IO AsyncServer. Pass None for batch/test mode.
        run_anomaly:  Whether to run the anomaly detection step.
        sample_rows:  If set, only read this many rows (fast schema inference).

    Returns:
        PipelineResult with df, profile, report, anomalies, and metadata.
    """
    import time

    start = time.monotonic()

    async def _emit(event: str, data: dict) -> None:
        if sio and dataset_id:
            with contextlib.suppress(Exception):
                await sio.emit(
                    event, {"dataset_id": dataset_id, **data}, room=f"dataset:{dataset_id}"
                )

    # ── Step 1: Ingest ────────────────────────────────────────────────────
    from backend.analytics_engine.ingestion.file_reader import FileReader

    df = await FileReader().read(storage_key, sample_rows=sample_rows)

    # ── Step 2: Profile ───────────────────────────────────────────────────
    profile = await profile_with_events(
        df=df,
        session_id=session_id,
        dataset_id=dataset_id,
        sio=sio,
    )

    # ── Step 3: Clean ─────────────────────────────────────────────────────
    await _emit("cleaning:start", {})
    from backend.analytics_engine.cleaning.data_cleaner import DataCleaner

    cleaned_df, report = await DataCleaner().clean(
        df, profile, session_id=session_id, dataset_id=dataset_id
    )
    await _emit(
        "cleaning:complete",
        {
            "rows_removed": report.rows_removed,
            "columns_removed": report.columns_removed,
            "steps": len(report.steps),
        },
    )

    # ── Step 4: Anomaly detection ─────────────────────────────────────────
    anomalies: list[dict] = []
    if run_anomaly:
        await _emit("anomaly:start", {})
        from backend.analytics_engine.anomaly_detection.anomaly_detector import AnomalyDetector

        detector = AnomalyDetector(run_isolation_forest=True)
        anomalies = await detector.detect(cleaned_df, profile=profile)

        # Emit per-anomaly events for the live anomaly ticker
        for a in anomalies[:50]:
            await _emit(
                "anomaly:detected",
                {
                    "column": a.get("column", ""),
                    "severity": a.get("severity", "low"),
                    "description": a.get("description", ""),
                },
            )
        await _emit("anomaly:complete", {"total_count": len(anomalies)})

    elapsed_ms = int((time.monotonic() - start) * 1000)

    return PipelineResult(
        df=cleaned_df,
        profile=profile,
        report=report,
        anomalies=anomalies,
        metadata={
            "pipeline_ms": elapsed_ms,
            "rows": getattr(profile, "row_count", 0),
            "columns": getattr(profile, "column_count", 0),
            "anomaly_count": len(anomalies),
        },
    )


async def profile_with_events(
    storage_key: str | None = None,
    df: pl.DataFrame | pd.DataFrame | None = None,
    session_id: str = "",
    dataset_id: str = "",
    sio: Any = None,  # noqa: ANN401
) -> DataProfile:
    """Profile a DataFrame and emit per-column Socket.IO events as each column finishes.

    Either ``storage_key`` or ``df`` must be provided. When ``storage_key``
    is given the file is loaded first.

    Real-time behaviour:
        The profiling loop runs in a ThreadPoolExecutor. After each column
        completes, the worker thread bridges back to the asyncio event loop
        via asyncio.run_coroutine_threadsafe() and emits:

            profiling:column_complete {column_name, column_index, total,
                                       progress (8-31%), profile}

        The frontend can render each column card as it arrives rather than
        waiting for all columns to complete — especially valuable for wide
        datasets (50+ columns) where profiling takes 3-5 seconds.

    Args:
        storage_key: S3 key or local path (loaded if df is None).
        df:          Pre-loaded DataFrame (skips file I/O).
        session_id:  AnalysisSession UUID.
        dataset_id:  Dataset UUID for Socket.IO room routing.
        sio:         Socket.IO AsyncServer (None = silent batch mode).

    Returns:
        DataProfile entity.
    """
    if df is None:
        if storage_key is None:
            raise ValueError("Either storage_key or df must be provided.")
        from backend.analytics_engine.ingestion.file_reader import FileReader

        df = await FileReader().read(storage_key)

    loop = asyncio.get_event_loop()
    col_count = len(df.columns) if hasattr(df, "columns") else df.shape[1]
    columns_done = [0]

    if sio and dataset_id:
        with contextlib.suppress(Exception):
            await sio.emit(
                "profiling:start",
                {"dataset_id": dataset_id, "column_count": col_count},
                room=f"dataset:{dataset_id}",
            )

    def _column_callback(col_name: str, col_profile: Any) -> None:  # noqa: ANN401
        """Called from the profiling thread after each column completes."""
        columns_done[0] += 1
        progress = 8 + int((columns_done[0] / max(col_count, 1)) * 23)  # 8% → 31%
        if sio and dataset_id:
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

    from backend.analytics_engine.profiling.data_profiler import DataProfiler

    profiler = DataProfiler()

    profile = await loop.run_in_executor(
        None,
        lambda: profiler._profile_sync_with_callback(
            df,
            session_id=session_id,
            dataset_id=dataset_id,
            column_callback=_column_callback,
        ),
    )

    if sio and dataset_id:
        with contextlib.suppress(Exception):
            await sio.emit(
                "profiling:complete",
                {
                    "dataset_id": dataset_id,
                    "row_count": getattr(profile, "row_count", 0),
                    "column_count": getattr(profile, "column_count", 0),
                    "completeness_score": getattr(profile, "completeness_score", 1.0),
                    "duplicate_count": getattr(profile, "duplicate_count", 0),
                },
                room=f"dataset:{dataset_id}",
            )

    return profile


async def stream_anomalies(
    df: pl.DataFrame | pd.DataFrame,
    profile: Any = None,  # noqa: ANN401
    sio: Any = None,  # noqa: ANN401
    dataset_id: str = "",
) -> list[dict]:
    """Run anomaly detection and stream each finding via Socket.IO as it's found.

    Emits ``anomaly:detected`` per anomaly (capped at 50 for UI performance)
    so the frontend can render an anomaly ticker in real-time without waiting
    for the full detection run.

    Args:
        df:         Cleaned DataFrame (output of DataCleaner).
        profile:    DataProfile entity (used for semantic type routing).
        sio:        Socket.IO AsyncServer.
        dataset_id: Dataset UUID for room routing.

    Returns:
        Full list of anomaly dicts sorted by severity then confidence.
    """
    from backend.analytics_engine.anomaly_detection.anomaly_detector import AnomalyDetector

    detector = AnomalyDetector(run_isolation_forest=True)
    anomalies = await detector.detect(df, profile=profile)

    if sio and dataset_id:
        for a in anomalies[:50]:
            with contextlib.suppress(Exception):
                await sio.emit(
                    "anomaly:detected",
                    {
                        "dataset_id": dataset_id,
                        "column": a.get("column", ""),
                        "severity": a.get("severity", "low"),
                        "anomaly_type": a.get("anomaly_type", "outlier"),
                        "description": a.get("description", ""),
                        "row_index": a.get("row_index"),
                        "confidence": a.get("confidence", 0.5),
                    },
                    room=f"dataset:{dataset_id}",
                )
        with contextlib.suppress(Exception):
            await sio.emit(
                "anomaly:complete",
                {"dataset_id": dataset_id, "total_count": len(anomalies)},
                room=f"dataset:{dataset_id}",
            )

    return anomalies


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------

__all__ = [
    # High-level async entry points (real-time applications)
    "run_pipeline",
    "profile_with_events",
    "stream_anomalies",
    # Result container
    "PipelineResult",
]
