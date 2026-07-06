"""Analytics __init__.py package."""
"""Analytics entities — mutable domain objects with identity."""
from backend.domain.analytics.entities.analysis_session import AnalysisSession
from backend.domain.analytics.entities.data_profile     import DataProfile
from backend.domain.analytics.entities.column_profile   import ColumnProfile, ColumnKind
from backend.domain.analytics.entities.cleaning_report  import CleaningReport, CleaningStep
from backend.domain.analytics.entities.anomaly_alert    import AnomalyAlert

__all__ = [
    "AnalysisSession", "DataProfile", "ColumnProfile", "ColumnKind",
    "CleaningReport", "CleaningStep", "AnomalyAlert",
]
