"""GetInsightsQuery — query DTO for fetching an InsightReport."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class GetInsightsQuery:
    dataset_id: str
    use_cache:  bool = True
