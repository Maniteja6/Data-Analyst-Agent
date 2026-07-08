"""InsightReport aggregate root — the AI-generated analysis output for a dataset."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from backend.domain.insight.events.insight_report_generated import InsightReportGenerated
from backend.shared.aggregate_root import AggregateRoot
from backend.shared.utils import new_uuid


@dataclass
class InsightReport(AggregateRoot):
    """Aggregate root for one AI-generated analysis report.

    Assembled by InsightAgent (insights, kpis) and RecommendationAgent
    (recommendations), then persisted by ReportNode. Served to the frontend
    via GetInsightsUseCase and exported to PDF/XLSX/PPTX via ExportReportUseCase.

    Attributes:
        id:                   Report UUID.
        session_id:           AnalysisSession this report belongs to.
        dataset_id:           Dataset this report was generated from.
        executive_summary:    LLM-streamed narrative summary.
        insights:              Ranked insight dicts (headline, explanation, business_impact, …).
        kpis:                  KPI card dicts computed from the DataProfile.
        anomaly_alerts:        Anomaly dicts surfaced during analysis (capped at 20).
        forecasts:              Forecast result dicts, if any target columns were forecastable.
        recommendations:        Recommended-action dicts filled in by RecommendationAgent.
        is_critic_validated:  True once the CriticAgent has approved the report.
        has_forecasts:          Derived flag — True if any forecasts were generated.
        has_anomalies:          Derived flag — True if any anomalies were detected.
        report_pdf_key:        S3 key of the rendered PDF, populated asynchronously.
        generated_at:           UTC timestamp when the report was created.
    """

    id: str
    session_id: str
    dataset_id: str
    executive_summary: str = ""
    insights: list[dict] = field(default_factory=list)
    kpis: list[dict] = field(default_factory=list)
    anomaly_alerts: list[dict] = field(default_factory=list)
    forecasts: list[dict] = field(default_factory=list)
    recommendations: list[dict] = field(default_factory=list)
    is_critic_validated: bool = False
    has_forecasts: bool = False
    has_anomalies: bool = False
    report_pdf_key: str | None = None
    generated_at: datetime | None = None

    def __post_init__(self) -> None:
        super().__init__()

    @classmethod
    def create(cls, session_id: str, dataset_id: str) -> InsightReport:
        """Factory — creates a new report and records InsightReportGenerated."""
        report = cls(
            id=new_uuid(),
            session_id=session_id,
            dataset_id=dataset_id,
            generated_at=datetime.now(UTC),
        )
        report._record_event(
            InsightReportGenerated(
                report_id=report.id,
                dataset_id=dataset_id,
                session_id=session_id,
            )
        )
        return report

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "dataset_id": self.dataset_id,
            "executive_summary": self.executive_summary,
            "insights": self.insights,
            "kpis": self.kpis,
            "anomaly_alerts": self.anomaly_alerts,
            "forecasts": self.forecasts,
            "recommendations": self.recommendations,
            "is_critic_validated": self.is_critic_validated,
            "has_forecasts": self.has_forecasts,
            "has_anomalies": self.has_anomalies,
            "report_pdf_key": self.report_pdf_key,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
        }
