"""Insights endpoints — retrieve AI-generated analysis reports."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
import structlog

from backend.api.dependencies import get_get_insights_use_case
from backend.api.schemas.insight_schemas import InsightReportResponse, InsightNotReadyResponse
from backend.application.queries.get_insights_query import GetInsightsQuery
from backend.domain.insight.exceptions import InsightReportNotFoundException

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/insights", tags=["insights"])


@router.get("/{dataset_id}", response_model=InsightReportResponse)
async def get_insights(
    dataset_id: str,
    use_cache:  bool = True,
    use_case=Depends(get_get_insights_use_case),
):
    """Return the InsightReport for a dataset.

    Returns 404 when the analysis has not completed yet.
    The frontend should redirect to the job polling endpoint in that case.
    """
    try:
        report = await use_case.execute(GetInsightsQuery(dataset_id=dataset_id, use_cache=use_cache))
        return InsightReportResponse(**{
            k: report.get(k, v)
            for k, v in InsightReportResponse.model_fields.items()
            if k in report
        })
    except InsightReportNotFoundException:
        raise HTTPException(status_code=404, detail="Insight report not yet available.")
