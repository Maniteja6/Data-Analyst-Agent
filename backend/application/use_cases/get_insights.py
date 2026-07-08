"""GetInsightsUseCase — retrieves the InsightReport, preferring Redis cache."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from backend.application.queries.get_insights_query import GetInsightsQuery
from backend.domain.insight.exceptions import InsightReportNotFoundException

if TYPE_CHECKING:
    from backend.application.ports.cache_port import ICacheService
    from backend.domain.insight.repositories.insight_repository import InsightRepository

logger = structlog.get_logger(__name__)


class GetInsightsUseCase:
    """Returns the InsightReport for a dataset, using the Redis cache as the fast path.

    Cache miss fallback:
      1. Load from Postgres via InsightRepository
      2. Populate the cache for subsequent requests
    """

    def __init__(self, insight_repo: InsightRepository, cache: ICacheService) -> None:
        self._repo = insight_repo
        self._cache = cache

    async def execute(self, query: GetInsightsQuery) -> dict:
        if query.use_cache:
            cached = await self._cache.get_json(f"insights:{query.dataset_id}")
            if isinstance(cached, dict):
                logger.debug("insights_cache_hit", dataset_id=query.dataset_id)
                return cached

        report = await self._repo.get_by_dataset_id(query.dataset_id)
        if report is None:
            raise InsightReportNotFoundException(query.dataset_id)

        result = report.to_dict()
        if query.use_cache:
            await self._cache.set_json(f"insights:{query.dataset_id}", result, ttl=86400)
        return result
