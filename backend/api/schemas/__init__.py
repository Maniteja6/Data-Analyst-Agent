"""Pydantic request/response schemas."""
"""Pydantic v2 request/response schemas for all API endpoints.

Common:       ErrorResponse, MessageResponse, PaginatedResponse
Datasets:     DatasetUploadResponse, DatasetStatusResponse
Insights:     InsightReportResponse, InsightNotReadyResponse
Conversations:CreateConversationRequest/Response, SendMessageRequest,
              MessageResponse, ConversationResponse
Exports:      ExportReportRequest, ExportReportResponse, ExportReadyResponse
"""
from backend.api.schemas.common_schemas       import ErrorResponse, MessageResponse
from backend.api.schemas.dataset_schemas      import DatasetUploadResponse
from backend.api.schemas.insight_schemas      import InsightReportResponse
from backend.api.schemas.conversation_schemas import (
    CreateConversationRequest, SendMessageRequest,
)
from backend.api.schemas.export_schemas       import ExportReportRequest

__all__ = [
    "ErrorResponse", "MessageResponse", "DatasetUploadResponse",
    "InsightReportResponse", "CreateConversationRequest",
    "SendMessageRequest", "ExportReportRequest",
]
