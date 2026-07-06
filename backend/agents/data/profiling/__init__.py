"""Agent sub-package."""
"""Profiling agent — DataProfiler integration with real-time column events.

ProfilingAgent bridges the sync DataProfiler thread back to the asyncio event
loop via asyncio.run_coroutine_threadsafe(), emitting profiling:column_complete
after each column so the browser renders column cards progressively.
"""
from backend.agents.data.profiling.profiling_agent    import ProfilingAgent
from backend.agents.data.profiling.correlation_analyzer import CorrelationAnalyzer
from backend.agents.data.profiling.histogram_builder  import HistogramBuilder
from backend.agents.data.profiling.statistics_calculator import StatisticsCalculator

__all__ = [
    "ProfilingAgent", "CorrelationAnalyzer", "HistogramBuilder", "StatisticsCalculator",
]
