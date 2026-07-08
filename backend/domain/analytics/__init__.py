"""Analytics bounded context — owns pipeline session state and data quality.

Aggregate:  AnalysisSession (pending → running → complete | failed)
Entities:   DataProfile, ColumnProfile, CleaningReport, AnomalyAlert
VOs:        StatisticalSummary, Histogram, CorrelationCoefficient
Service:    DataQualityScorer → QualityReport (completeness/consistency/grade)
Repository: SessionRepository ABC
"""

from backend.domain.analytics.entities.analysis_session import AnalysisSession
from backend.domain.analytics.entities.cleaning_report import CleaningReport
from backend.domain.analytics.entities.data_profile import DataProfile
from backend.domain.analytics.services.data_quality_scorer import DataQualityScorer

__all__ = ["AnalysisSession", "DataProfile", "CleaningReport", "DataQualityScorer"]
