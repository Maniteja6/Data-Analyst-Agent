"""Insight request/response Pydantic schemas."""
from __future__ import annotations
from pydantic import BaseModel
from typing import Any


class InsightReportResponse(BaseModel):
    id:                  str
    session_id:          str
    dataset_id:          str
    executive_summary:   str                = ""
    insights:            list[dict]         = []
    kpis:                list[dict]         = []
    anomaly_alerts:      list[dict]         = []
    forecasts:           list[dict]         = []
    recommendations:     list[dict]         = []
    is_critic_validated: bool               = False
    has_forecasts:       bool               = False
    has_anomalies:       bool               = False
    generated_at:        str | None         = None
    report_pdf_key:      str | None         = None


class InsightNotReadyResponse(BaseModel):
    dataset_id: str
    status:     str = "processing"
    message:    str = "Analysis is still in progress. Please try again shortly."
