"""Insight bounded context — owns AI-generated analysis output.

Aggregate: InsightReport (executive_summary, insights, kpis, anomalies,
           forecasts, recommendations, is_critic_validated)
Service:   KPICalculator → list[KPI]
Event:     InsightReportGenerated
"""
from backend.domain.insight.entities.insight_report import InsightReport
from backend.domain.insight.services.kpi_calculator import KPICalculator

__all__ = ["InsightReport", "KPICalculator"]
