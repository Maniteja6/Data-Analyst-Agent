"""Statistical analysis — correlation, distribution fitting, hypothesis testing, trend analysis."""
"""Statistics — correlation, trend, hypothesis testing, and distribution fitting.

CorrelationEngine:   pairwise Pearson r; filters |r| >= min_abs_r; polars-first.
TrendAnalyzer:       np.polyfit on date ordinals; slope, R², direction, pct_change.
HypothesisTester:    Welch t-test and chi-square independence test (scipy).
DistributionFitter:  tests norm/expon/lognorm/gamma/beta via scipy kstest.
"""
from backend.analytics_engine.statistics.correlation_engine import CorrelationEngine
from backend.analytics_engine.statistics.trend_analyzer     import TrendAnalyzer

__all__ = ["CorrelationEngine", "TrendAnalyzer"]
