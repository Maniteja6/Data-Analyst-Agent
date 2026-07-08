"""Insights endpoints — retrieve AI-generated analysis reports."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from backend.api.dependencies import get_get_insights_use_case
from backend.api.schemas.insight_schemas import InsightReportResponse
from backend.application.queries.get_insights_query import GetInsightsQuery
from backend.domain.insight.exceptions import InsightReportNotFoundException
from fastapi import APIRouter, Depends, HTTPException

if TYPE_CHECKING:
    from backend.application.use_cases.get_insights import GetInsightsUseCase

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/insights", tags=["insights"])


@router.get("/{dataset_id}", response_model=InsightReportResponse)
async def get_insights(
    dataset_id: str,
    use_cache: bool = True,
    use_case: GetInsightsUseCase = Depends(get_get_insights_use_case),
) -> InsightReportResponse:
    """Return the InsightReport for a dataset.

    Returns 404 when the analysis has not completed yet.
    The frontend should redirect to the job polling endpoint in that case.
    """
    try:
        report = await use_case.execute(
            GetInsightsQuery(dataset_id=dataset_id, use_cache=use_cache)
        )
        return InsightReportResponse(
            **{
                k: report.get(k, v)
                for k, v in InsightReportResponse.model_fields.items()
                if k in report
            }
        )
    except InsightReportNotFoundException as exc:
        raise HTTPException(status_code=404, detail="Insight report not yet available.") from exc
