"""Read-only query DTOs — no side effects, always return typed result objects.

GetDatasetQuery        → DatasetResult
GetInsightsQuery       → InsightReportResponse | InsightNotReadyResponse
GetConversationQuery   → ConversationResult
GetJobStatusQuery      → JobStatusResult  (Redis hash → Celery fallback)
"""

from backend.application.queries.get_conversation import GetConversationQuery
from backend.application.queries.get_dataset import GetDatasetQuery
from backend.application.queries.get_insights import GetInsightsQuery
from backend.application.queries.get_job_status import GetJobStatusQuery

__all__ = [
    "GetDatasetQuery",
    "GetInsightsQuery",
    "GetConversationQuery",
    "GetJobStatusQuery",
]
