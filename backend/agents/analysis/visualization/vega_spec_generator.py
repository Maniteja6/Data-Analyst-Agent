"""Vega-Lite v5 specification generators.

Each function returns a complete, valid Vega-Lite JSON specification dict
that can be passed directly to the frontend's ``VegaEmbed`` component.

Design decisions:
- ``width: "container"`` makes charts responsive to their parent element
- ``height: 240`` is the default; callers can override
- ``#5B4FE8`` is the DataPilot brand violet, used for single-series charts
- ``tooltip: [{"type": "quantitative"}, ...]`` gives hover detail by default
"""
from __future__ import annotations
from typing import Any

BRAND_COLOUR = "#5B4FE8"
SCHEMA       = "https://vega.github.io/schema/vega-lite/v5.json"
DEFAULT_H    = 240
DEFAULT_W    = "container"


def build_line_spec(
    data: list[dict],
    x: str,
    y: str,
    title: str = "",
    color: str = BRAND_COLOUR,
    height: int = DEFAULT_H,
) -> dict[str, Any]:
    """Temporal line chart — best for time series."""
    return {
        "$schema": SCHEMA,
        "title":   title,
        "mark":    {"type": "line", "color": color, "strokeWidth": 2, "point": True},
        "data":    {"values": data},
        "encoding": {
            "x": {"field": x, "type": "temporal",    "title": x,
                  "axis":  {"format": "%b %d", "labelAngle": -30}},
            "y": {"field": y, "type": "quantitative", "title": y},
            "tooltip": [
                {"field": x, "type": "temporal",    "title": x, "format": "%Y-%m-%d"},
                {"field": y, "type": "quantitative", "title": y, "format": ",.2f"},
            ],
        },
        "width":  DEFAULT_W,
        "height": height,
    }


def build_bar_spec(
    data: list[dict],
    x: str,
    y: str,
    title: str = "",
    horizontal: bool = False,
    color: str = BRAND_COLOUR,
    height: int = DEFAULT_H,
) -> dict[str, Any]:
    """Categorical bar chart — best for group comparisons."""
    if horizontal:
        encoding = {
            "x": {"field": y, "type": "quantitative", "title": y},
            "y": {"field": x, "type": "nominal",      "title": x,
                  "sort":  "-x"},
            "color": {"value": color},
            "tooltip": [
                {"field": x, "type": "nominal"},
                {"field": y, "type": "quantitative", "format": ",.2f"},
            ],
        }
    else:
        encoding = {
            "x": {"field": x, "type": "nominal",      "title": x,
                  "axis":  {"labelAngle": -30}},
            "y": {"field": y, "type": "quantitative", "title": y},
            "color": {"value": color},
            "tooltip": [
                {"field": x, "type": "nominal"},
                {"field": y, "type": "quantitative", "format": ",.2f"},
            ],
        }
    return {
        "$schema": SCHEMA,
        "title":   title,
        "mark":    {"type": "bar"},
        "data":    {"values": data},
        "encoding": encoding,
        "width":   DEFAULT_W,
        "height":  height,
    }


def build_scatter_spec(
    data: list[dict],
    x: str,
    y: str,
    color_col: str | None = None,
    title: str = "",
    height: int = DEFAULT_H,
) -> dict[str, Any]:
    """Scatter / point chart — best for bivariate correlation."""
    encoding: dict[str, Any] = {
        "x": {"field": x, "type": "quantitative", "title": x},
        "y": {"field": y, "type": "quantitative", "title": y},
        "tooltip": [
            {"field": x, "type": "quantitative"},
            {"field": y, "type": "quantitative"},
        ],
        "opacity": {"value": 0.7},
    }
    if color_col:
        encoding["color"] = {"field": color_col, "type": "nominal"}
    else:
        encoding["color"] = {"value": BRAND_COLOUR}

    return {
        "$schema": SCHEMA,
        "title":   title,
        "mark":    {"type": "point", "filled": True, "size": 60},
        "data":    {"values": data},
        "encoding": encoding,
        "width":   DEFAULT_W,
        "height":  height,
    }


def build_histogram_spec(
    data: list[dict],
    x: str,
    bin_count: int = 20,
    title: str = "",
    color: str = BRAND_COLOUR,
    height: int = DEFAULT_H,
) -> dict[str, Any]:
    """Distribution histogram — best for single numeric column."""
    return {
        "$schema": SCHEMA,
        "title":   title or f"Distribution of {x}",
        "mark":    {"type": "bar", "color": color},
        "data":    {"values": data},
        "encoding": {
            "x": {
                "field": x,
                "type":  "quantitative",
                "bin":   {"maxbins": bin_count},
                "title": x,
            },
            "y": {
                "aggregate": "count",
                "type":      "quantitative",
                "title":     "Count",
            },
            "tooltip": [
                {"field": x, "type": "quantitative", "bin": True},
                {"aggregate": "count", "type": "quantitative", "title": "Count"},
            ],
        },
        "width":  DEFAULT_W,
        "height": height,
    }
