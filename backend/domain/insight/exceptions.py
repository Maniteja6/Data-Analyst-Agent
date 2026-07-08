"""Insight domain exceptions."""

from __future__ import annotations

from backend.shared.exceptions import DomainError


class InsightError(DomainError):
    """Base exception for the insight bounded context."""


class InsightReportNotFoundException(InsightError):  # noqa: N818 — name fixed by existing call sites
    """Raised when no InsightReport exists yet for a dataset.

    Maps to HTTP 404 at the API boundary — the analysis pipeline has not
    finished generating the report yet.
    """

    def __init__(self, dataset_id: str) -> None:
        super().__init__(
            f"InsightReport for dataset '{dataset_id}' not found.",
            code="INSIGHT_REPORT_NOT_FOUND",
        )
        self.dataset_id = dataset_id
