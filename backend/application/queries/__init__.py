"""Read-only query DTOs — no side effects, always return typed result objects.

GetDatasetQuery        → DatasetResult
GetInsightsQuery       → InsightReportResponse | InsightNotReadyResponse
GetConversationQuery   → ConversationResult
GetJobStatusQuery      → JobStatusResult  (Redis hash → Celery fallback)
"""

from backend.application.queries.get_conversation_query import GetConversationQuery
from backend.application.queries.get_dataset_query import GetDatasetQuery
from backend.application.queries.get_insights_query import GetInsightsQuery
from backend.application.queries.get_job_status_query import GetJobStatusQuery

__all__ = [
    "GetDatasetQuery",
    "GetInsightsQuery",
    "GetConversationQuery",
    "GetJobStatusQuery",
]
