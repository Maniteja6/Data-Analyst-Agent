"""HistogramBuilder — converts DataProfiler Histogram VOs into JSON-ready dicts.

Real-time design:
    Histograms are embedded directly in the ``profiling:column_complete``
    Socket.IO event payload so the frontend can render distribution charts
    without a separate API call.

    Histogram data is intentionally compact — only bin_edges and bin_counts
    are sent (Vega-Lite can compute display labels client-side).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.domain.analytics.value_objects.histogram import Histogram


class HistogramBuilder:
    """Converts Histogram value objects to JSON-serialisable dicts."""

    def to_dict(self, histogram: Histogram | None) -> dict[str, Any] | None:
        """Convert a Histogram VO to a dict for Socket.IO / API responses.

        Args:
            histogram: Histogram entity or None.

        Returns:
            Dict with keys: type, bin_edges, bin_counts, bin_labels,
            total_count. Returns None when histogram is None.
        """
        if histogram is None:
            return None

        return {
            "type": getattr(histogram, "histogram_type", "numeric"),
            "bin_edges": _safe_list(getattr(histogram, "bin_edges", [])),
            "bin_counts": _safe_list(getattr(histogram, "bin_counts", [])),
            "bin_labels": _safe_list(getattr(histogram, "bin_labels", [])),
            "total_count": int(getattr(histogram, "total_count", 0)),
        }

    def to_vega_histogram(
        self,
        histogram: Histogram | None,
        column_name: str,
        color: str = "#5B4FE8",
    ) -> dict[str, Any] | None:
        """Build a complete Vega-Lite histogram spec from a Histogram VO.

        Args:
            histogram:   Histogram VO.
            column_name: Used for chart axis labels.
            color:       Brand colour for bars (default DataPilot violet).

        Returns:
            Vega-Lite v5 spec dict ready for VegaEmbed.
        """
        h = self.to_dict(histogram)
        if not h:
            return None

        # Build values array for Vega-Lite
        bin_edges = h["bin_edges"]
        bin_counts = h["bin_counts"]
        bin_labels = h.get("bin_labels") or []

        if bin_labels:
            # Categorical histogram (value_counts format)
            values = [
                {"label": label, "count": count}
                for label, count in zip(bin_labels, bin_counts, strict=False)
            ]
            return {
                "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                "mark": {"type": "bar", "color": color},
                "data": {"values": values},
                "encoding": {
                    "x": {
                        "field": "label",
                        "type": "nominal",
                        "title": column_name,
                        "axis": {"labelAngle": -30},
                    },
                    "y": {"field": "count", "type": "quantitative", "title": "Count"},
                    "tooltip": [
                        {"field": "label", "type": "nominal"},
                        {"field": "count", "type": "quantitative"},
                    ],
                },
                "width": "container",
                "height": 180,
            }
        elif len(bin_edges) >= 2:
            # Numeric histogram (pre-binned)
            values = [
                {"bin_start": bin_edges[i], "bin_end": bin_edges[i + 1], "count": bin_counts[i]}
                for i in range(len(bin_counts))
            ]
            return {
                "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                "mark": {"type": "bar", "color": color},
                "data": {"values": values},
                "encoding": {
                    "x": {
                        "field": "bin_start",
                        "type": "quantitative",
                        "title": column_name,
                        "bin": {"binned": True},
                        "scale": {"zero": False},
                    },
                    "x2": {"field": "bin_end"},
                    "y": {"field": "count", "type": "quantitative", "title": "Count"},
                    "tooltip": [
                        {"field": "bin_start", "type": "quantitative", "title": "From"},
                        {"field": "bin_end", "type": "quantitative", "title": "To"},
                        {"field": "count", "type": "quantitative"},
                    ],
                },
                "width": "container",
                "height": 180,
            }
        return None


def _safe_list(value: Any) -> list:  # noqa: ANN401
    """Coerce to a plain Python list for JSON serialisation."""
    if value is None:
        return []
    try:
        return list(value)
    except TypeError:
        return []
