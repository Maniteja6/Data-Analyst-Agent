"""Chart type selector — maps data characteristics to optimal Vega-Lite marks.

Selection logic (priority order):
1. If datetime + numeric → line chart
2. If categorical + numeric → bar chart (horizontal if > 8 categories)
3. If two numeric columns → scatter (point) chart
4. If one numeric column → histogram
5. Default → bar chart
"""
from __future__ import annotations

DATE_TYPES    = frozenset({"date", "datetime"})
NUMERIC_TYPES = frozenset({"currency", "numeric_measure", "numeric_count", "percentage"})
CAT_TYPES     = frozenset({"categorical"})


def select_chart_type(
    col_types: dict[str, str],
    intent: str = "",
    row_count: int = 0,
) -> dict:
    """Select the best chart type given column semantic types and user intent.

    Args:
        col_types:  Dict of column_name → semantic_type for the result set.
        intent:     Optional user intent string (e.g. "trend", "compare",
                    "distribution") to bias chart selection.
        row_count:  Number of data rows (used for histogram bin sizing).

    Returns:
        Dict with keys: ``mark``, ``x_type``, ``y_type``, ``orient``,
        ``bin_count`` (for histograms).
    """
    date_cols    = [n for n, t in col_types.items() if t in DATE_TYPES]
    numeric_cols = [n for n, t in col_types.items() if t in NUMERIC_TYPES]
    cat_cols     = [n for n, t in col_types.items() if t in CAT_TYPES]

    intent_lower = intent.lower()

    # ── User intent overrides ─────────────────────────────────────────────
    if "trend" in intent_lower or "over time" in intent_lower:
        if date_cols and numeric_cols:
            return {"mark": "line", "x_type": "temporal", "y_type": "quantitative"}

    if "distribut" in intent_lower or "histogram" in intent_lower:
        if numeric_cols:
            return _histogram(row_count)

    if "scatter" in intent_lower or "correlat" in intent_lower:
        if len(numeric_cols) >= 2:
            return {"mark": "point", "x_type": "quantitative", "y_type": "quantitative"}

    # ── Automatic selection ───────────────────────────────────────────────
    if date_cols and numeric_cols:
        return {"mark": "line", "x_type": "temporal", "y_type": "quantitative"}

    if cat_cols and numeric_cols:
        n_cats = len(cat_cols)
        orient = "horizontal" if n_cats > 8 else "vertical"
        return {
            "mark":   "bar",
            "x_type": "nominal",
            "y_type": "quantitative",
            "orient": orient,
        }

    if len(numeric_cols) >= 2:
        return {"mark": "point", "x_type": "quantitative", "y_type": "quantitative"}

    if len(numeric_cols) == 1:
        return _histogram(row_count)

    return {"mark": "bar", "x_type": "nominal", "y_type": "quantitative"}


def _histogram(row_count: int) -> dict:
    bin_count = min(30, max(5, row_count // 50)) if row_count else 20
    return {
        "mark":      "bar",
        "x_type":    "quantitative",
        "y_type":    "quantitative",
        "bin_count": bin_count,
        "is_histogram": True,
    }
