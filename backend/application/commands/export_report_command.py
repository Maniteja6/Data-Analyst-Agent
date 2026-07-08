"""ExportReportCommand — input DTO for the ExportReportUseCase."""

from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_FORMATS = frozenset({"pdf", "xlsx", "pptx", "json"})


@dataclass(frozen=True)
class ExportReportCommand:
    """Request to generate and upload an export of an InsightReport.

    Attributes:
        dataset_id:     Source dataset UUID.
        session_id:     Analysis session whose InsightReport is to be exported.
        format:         Output format: ``'pdf'`` | ``'xlsx'`` | ``'pptx'`` | ``'json'``.
        correlation_id: Request-scoped tracing ID.
    """

    dataset_id: str
    session_id: str
    format: str
    correlation_id: str = ""

    def __post_init__(self) -> None:
        if self.format not in SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported format '{self.format}'. "
                f"Supported: {', '.join(sorted(SUPPORTED_FORMATS))}"
            )
