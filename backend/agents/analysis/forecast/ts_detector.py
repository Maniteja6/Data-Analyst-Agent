"""Time series detector — identifies datetime and numeric columns for forecasting."""
from __future__ import annotations


def detect_time_series_columns(schema: dict) -> list[str]:
    """Return column names whose semantic type is date or datetime.

    Args:
        schema: Dataset schema dict with a ``columns`` list, each entry
                having ``name`` and ``semantic_type``.

    Returns:
        Ordered list of date/datetime column names.
    """
    return [
        col["name"]
        for col in schema.get("columns", [])
        if col.get("semantic_type") in ("date", "datetime")
    ]


def detect_numeric_targets(schema: dict) -> list[str]:
    """Return column names suitable as forecast targets (numeric types).

    Prioritises currency and numeric_measure over count columns.
    """
    priority = {"currency": 0, "numeric_measure": 1, "numeric_count": 2}
    candidates = [
        col for col in schema.get("columns", [])
        if col.get("semantic_type") in priority
    ]
    candidates.sort(key=lambda c: priority.get(c.get("semantic_type", ""), 99))
    return [c["name"] for c in candidates]


def is_forecasting_viable(schema: dict, min_rows: int = 30) -> dict:
    """Determine whether forecasting is viable for this dataset.

    Returns a dict with ``viable`` flag and ``reason`` string.
    """
    date_cols    = detect_time_series_columns(schema)
    numeric_cols = detect_numeric_targets(schema)
    row_count    = schema.get("row_count_sample", 0)

    if not date_cols:
        return {"viable": False, "reason": "No datetime columns detected"}
    if not numeric_cols:
        return {"viable": False, "reason": "No numeric target columns detected"}
    if row_count < min_rows:
        return {
            "viable": False,
            "reason": f"Insufficient data ({row_count} rows, need ≥ {min_rows})",
        }
    return {
        "viable":       True,
        "date_cols":    date_cols,
        "target_cols":  numeric_cols,
        "reason":       "Forecasting conditions met",
    }
