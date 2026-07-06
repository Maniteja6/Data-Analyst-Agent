"""Job queue — Celery app, tasks, and job adapter."""
"""Celery job queue — 3 queues, 3 worker pools.

    analysis  (4 workers, CPU-bound)  — profiling, cleaning, anomaly detection
    agents    (2 workers, I/O-bound)  — LangGraph pipeline + Bedrock API calls
    reports   (1 worker, disk-bound)  — PDF/XLSX/PPTX render + S3 upload

CeleryJobAdapter: enqueue_analysis/agents/report → task_id: str.
NullJobAdapter:   fake task IDs; no broker required (unit/integration tests).
"""
from backend.infrastructure.job_queue.celery_job_adapter import CeleryJobAdapter

__all__ = ["CeleryJobAdapter"]
