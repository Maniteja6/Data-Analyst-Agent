"""Use case implementations."""
"""Use cases — orchestrate domain logic and port calls. No I/O logic here.

    UploadDatasetUseCase     — checksum dedup + S3 + DatasetRepository + Celery
    RunAnalysisUseCase       — short-circuits if already READY; enqueues agents
    GetDatasetUseCase        — DatasetRepository → DatasetResult
    GetInsightsUseCase       — Redis-first (24h TTL) → Postgres fallback
    GetJobStatusUseCase      — Redis hash → Celery AsyncResult fallback
    CreateConversationUseCase— Conversation aggregate + Redis episodic init
    SendMessageUseCase       — SecurityAgent → chat_query_graph → MemoryAgent
    ExportReportUseCase      — validates format + enqueues report Celery task
"""
from backend.application.use_cases.upload_dataset    import UploadDatasetUseCase
from backend.application.use_cases.run_analysis      import RunAnalysisUseCase
from backend.application.use_cases.get_dataset       import GetDatasetUseCase
from backend.application.use_cases.get_insights      import GetInsightsUseCase
from backend.application.use_cases.get_job_status    import GetJobStatusUseCase
from backend.application.use_cases.create_conversation import CreateConversationUseCase
from backend.application.use_cases.send_message      import SendMessageUseCase
from backend.application.use_cases.export_report     import ExportReportUseCase

__all__ = [
    "UploadDatasetUseCase", "RunAnalysisUseCase", "GetDatasetUseCase",
    "GetInsightsUseCase", "GetJobStatusUseCase", "CreateConversationUseCase",
    "SendMessageUseCase", "ExportReportUseCase",
]
