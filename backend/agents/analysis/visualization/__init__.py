"""Agent sub-package."""
"""Visualization agent — Vega-Lite v5 chart spec generation.

ChartTypeSelector: temporal+numeric→line, categorical+numeric→bar,
                   two numeric→scatter, one numeric→histogram.
VegaSpecGenerator: build_line_spec, build_bar_spec, build_scatter_spec,
                   build_histogram_spec — all return complete Vega-Lite dicts.
"""
from backend.agents.analysis.visualization.visualization_agent import VisualizationAgent
from backend.agents.analysis.visualization.chart_type_selector import select_chart_type
from backend.agents.analysis.visualization.vega_spec_generator import (
    build_line_spec, build_bar_spec, build_scatter_spec, build_histogram_spec,
)

__all__ = [
    "VisualizationAgent", "select_chart_type",
    "build_line_spec", "build_bar_spec", "build_scatter_spec", "build_histogram_spec",
]
