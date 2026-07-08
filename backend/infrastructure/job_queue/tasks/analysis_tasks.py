"""Celery tasks for the analytics pipeline.

Queue: ``analysis``
Typical worker flags: ``--concurrency=2`` (CPU-bound; polars / scikit-learn)

Pipeline stages (executed sequentially within one task):
    1. FileReader       — load CSV/Parquet/Excel into a polars DataFrame
    2. SchemaAgent      — infer column types and semantic classification
    3. DataProfiler     — compute per-column statistics and histograms
    4. DataCleaner      — remove duplicates, impute nulls, coerce types
    5. AnomalyDetector  — IQR + Z-score + Isolation Forest on cleaned data
    6. ColumnStatsWriter — persist statistics to ClickHouse (optional)
    7. Dataset.mark_ready() — transition aggregate and emit DatasetReady event

Progress is written to Redis at each stage so the WebSocket gateway can
push real-time updates to the browser's upload progress bar.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC
from typing import TYPE_CHECKING, Any

import structlog
from backend.infrastructure.job_queue.celery_app import celery_app

if TYPE_CHECKING:
    from celery import Task

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Main pipeline task
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="analysis.run_pipeline",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def run_analysis_pipeline(
    self: Task,
    dataset_id: str,
    storage_key: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Run the full analytics pipeline for a newly uploaded dataset.

    Executes synchronously inside the Celery worker process using
    ``asyncio.run()`` to drive async infrastructure adapters (S3, Postgres,
    Bedrock for schema classification, Redis for progress updates).

    Args:
        dataset_id:     UUID of the Dataset aggregate to process.
        storage_key:    S3/MinIO object key for the raw file.
        correlation_id: Request-scoped tracing ID for log correlation.

    Returns:
        Summary dict: ``{dataset_id, row_count, column_count, anomaly_count, status}``.

    Retry policy:
        Retries up to 3 times with a 30-second delay on any exception.
        The Dataset aggregate is transitioned to FAILED on final failure.
    """
    logger.info(
        "analysis_pipeline_start",
        task_id=self.request.id,
        dataset_id=dataset_id,
    )
    start = time.monotonic()

    try:
        result = asyncio.run(
            _run_pipeline_async(
                task=self,
                dataset_id=dataset_id,
                storage_key=storage_key,
                correlation_id=correlation_id,
            )
        )
        duration = round(time.monotonic() - start, 2)
        logger.info(
            "analysis_pipeline_complete",
            dataset_id=dataset_id,
            duration_seconds=duration,
            **result,
        )
        return result

    except Exception as exc:
        logger.error(
            "analysis_pipeline_failed",
            dataset_id=dataset_id,
            error=str(exc),
            attempt=self.request.retries + 1,
        )
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc) from exc
        # Final failure — mark the dataset as failed in Postgres
        asyncio.run(_mark_dataset_failed(dataset_id, str(exc)))
        raise


# ---------------------------------------------------------------------------
# Maintenance task (scheduled via beat)
# ---------------------------------------------------------------------------


@celery_app.task(name="analysis.cleanup_stale_jobs")
def cleanup_stale_jobs() -> dict:
    """Periodic task that finds and recovers stuck analysis jobs.

    Runs every 30 minutes (configured in ``celery_app.beat_schedule``).
    Looks for Dataset rows that have been in PROFILING or CLEANING status
    for more than 2 hours and marks them as FAILED, freeing the user to
    retry the upload.

    Returns:
        ``{recovered_count: int, dataset_ids: list[str]}``.
    """
    return asyncio.run(_cleanup_stale_jobs_async())


# ---------------------------------------------------------------------------
# Async implementation
# ---------------------------------------------------------------------------


async def _run_pipeline_async(
    task: Task,
    dataset_id: str,
    storage_key: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Core async pipeline logic executed inside ``asyncio.run()``."""
    from backend.analytics_engine.anomaly_detection.anomaly_detector import AnomalyDetector
    from backend.analytics_engine.cleaning.data_cleaner import DataCleaner
    from backend.analytics_engine.ingestion.file_reader import FileReader
    from backend.analytics_engine.profiling.data_profiler import DataProfiler
    from backend.infrastructure.analytics_db.column_stats_writer import ColumnStatsWriter
    from backend.infrastructure.cache.redis_cache_adapter import get_redis_cache

    cache = get_redis_cache()
    job_id = task.request.id

    async def progress(step: str, pct: int) -> None:
        await cache.cache_job_status(
            job_id=job_id,
            status="running",
            progress=pct,
            step=step,
            extra={"dataset_id": dataset_id, "correlation_id": correlation_id},
        )
        # Pub/sub notification → WebSocket gateway
        import json

        await cache.publish(
            f"dataset:{dataset_id}",
            json.dumps(
                {
                    "type": "job.progress",
                    "job_id": job_id,
                    "progress": pct / 100,
                    "message": step,
                    "dataset_id": dataset_id,
                }
            ),
        )

    # ── Stage 1: Read file ────────────────────────────────────────────────
    await progress("Reading file…", 10)
    reader = FileReader()
    df = await reader.read(storage_key, sample_rows=None)

    # ── Stage 2: Profile ──────────────────────────────────────────────────
    await progress("Profiling columns…", 30)
    profiler = DataProfiler()
    profile = await profiler.profile(df)

    # ── Stage 3: Clean ────────────────────────────────────────────────────
    await progress("Cleaning data…", 55)
    cleaner = DataCleaner()
    cleaned_df, cleaning_report = await cleaner.clean(df, profile)

    # ── Stage 4: Detect anomalies ─────────────────────────────────────────
    await progress("Detecting anomalies…", 75)
    detector = AnomalyDetector()
    anomalies = await detector.detect(cleaned_df, profile)

    # ── Stage 5: Write to ClickHouse (optional) ───────────────────────────
    await progress("Persisting statistics…", 88)
    writer = ColumnStatsWriter()
    await writer.write_profile(
        dataset_id=dataset_id,
        session_id=job_id,
        profile=profile,
    )

    # ── Stage 6: Persist results and mark dataset READY ───────────────────
    await progress("Finalising…", 95)
    await _persist_results(
        dataset_id=dataset_id,
        profile=profile,
        cleaning_report=cleaning_report,
        anomaly_count=len(anomalies),
        correlation_id=correlation_id,
    )

    await progress("Ready", 100)
    await cache.cache_job_status(
        job_id=job_id,
        status="complete",
        progress=100,
        step="Analysis complete",
        extra={"dataset_id": dataset_id},
    )

    return {
        "dataset_id": dataset_id,
        "row_count": profile.row_count,
        "column_count": profile.column_count,
        "anomaly_count": len(anomalies),
        "status": "complete",
    }


async def _persist_results(
    dataset_id: str,
    profile: Any,  # noqa: ANN401
    cleaning_report: Any,  # noqa: ANN401
    anomaly_count: int,
    correlation_id: str,
) -> None:
    """Persist analysis results and transition the Dataset aggregate to READY."""
    try:
        from backend.infrastructure.messaging.kafka_event_bus import KafkaEventBus
        from backend.infrastructure.persistence.database import get_session
        from backend.infrastructure.persistence.repositories.postgres_dataset_repository import (
            PostgresDatasetRepository,
        )

        async with get_session() as session:
            repo = PostgresDatasetRepository(session)
            dataset = await repo.get_by_id(dataset_id)
            if dataset is None:
                logger.warning("dataset_not_found_during_persist", dataset_id=dataset_id)
                return

            schema = dataset.schema_json or {}
            dataset.mark_ready(
                row_count=profile.row_count,
                column_count=profile.column_count,
                schema=schema,
            )
            await repo.save(dataset)

            # Publish domain events to Kafka
            bus = KafkaEventBus()
            await bus.start()
            try:
                for event in dataset.pull_domain_events():
                    await bus.publish(event, partition_key=dataset_id)
            finally:
                await bus.stop()

    except Exception as exc:
        logger.error("persist_results_failed", dataset_id=dataset_id, error=str(exc))
        raise


async def _mark_dataset_failed(dataset_id: str, reason: str) -> None:
    """Transition the Dataset aggregate to FAILED after all retries exhausted."""
    try:
        from backend.infrastructure.persistence.database import get_session
        from backend.infrastructure.persistence.repositories.postgres_dataset_repository import (
            PostgresDatasetRepository,
        )

        async with get_session() as session:
            repo = PostgresDatasetRepository(session)
            dataset = await repo.get_by_id(dataset_id)
            if dataset:
                dataset.mark_failed(reason[:500])
                await repo.save(dataset)
    except Exception as exc:
        logger.error("mark_dataset_failed_error", dataset_id=dataset_id, error=str(exc))


async def _cleanup_stale_jobs_async() -> dict:
    """Implementation of the stale-job cleanup beat task."""
    from datetime import datetime, timedelta

    try:
        from backend.domain.dataset.value_objects.dataset_status import DatasetStatus
        from backend.infrastructure.persistence.database import get_session
        from backend.infrastructure.persistence.repositories.postgres_dataset_repository import (
            PostgresDatasetRepository,
        )

        cutoff = datetime.now(UTC) - timedelta(hours=2)
        recovered = []

        for status in [DatasetStatus.PROFILING, DatasetStatus.CLEANING]:
            async with get_session() as session:
                repo = PostgresDatasetRepository(session)
                datasets = await repo.get_by_status(status)
                for ds in datasets:
                    if ds.updated_at and ds.updated_at < cutoff:
                        ds.mark_failed("Pipeline stalled — auto-recovered by watchdog")
                        await repo.save(ds)
                        recovered.append(ds.id)

        logger.info("stale_jobs_recovered", count=len(recovered))
        return {"recovered_count": len(recovered), "dataset_ids": recovered}

    except Exception as exc:
        logger.error("stale_job_cleanup_failed", error=str(exc))
        return {"recovered_count": 0, "dataset_ids": [], "error": str(exc)}
