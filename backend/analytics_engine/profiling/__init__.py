"""Statistical profiling — numeric, categorical, datetime, and text profilers."""
"""Profiling — per-column statistical analysis with callback support.

DataProfiler:        orchestrates all column profilers; accepts column_callback
                     called after each column for real-time Socket.IO events.
NumericProfiler:     StatisticalSummary (mean/stddev/P5-P95/skew/kurt) + Histogram.
CategoricalProfiler: top-N value_counts + cardinality ratio + categorical Histogram.
DatetimeProfiler:    min/max date, inferred frequency, null gaps.
TextProfiler:        length stats, whitespace, email/URL detection.
"""
from backend.analytics_engine.profiling.data_profiler import DataProfiler

__all__ = ["DataProfiler"]
