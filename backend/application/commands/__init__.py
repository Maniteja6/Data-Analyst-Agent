"""Command data classes."""
"""Immutable input DTOs for all write operations.

All commands are frozen Pydantic models.
Commands carry a correlation_id so the full request chain is traceable
from HTTP header → Kafka message → Redis pub/sub → Socket.IO event.

    UploadDatasetCommand    — filename, file_obj, size_bytes, mime_type, project_id
    RunAnalysisCommand      — dataset_id, force_rerun
    SendMessageCommand      — conversation_id, dataset_id, content, stream
    ExportReportCommand     — dataset_id, session_id, format (pdf|xlsx|pptx|json)
"""
from backend.application.commands.upload_dataset  import UploadDatasetCommand
from backend.application.commands.run_analysis    import RunAnalysisCommand
from backend.application.commands.send_message    import SendMessageCommand
from backend.application.commands.export_report   import ExportReportCommand

__all__ = [
    "UploadDatasetCommand", "RunAnalysisCommand",
    "SendMessageCommand", "ExportReportCommand",
]
