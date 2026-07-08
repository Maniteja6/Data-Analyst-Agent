"""has_time_series — edge condition for the analysis pipeline graph.

Inspects the pipeline state after profiling to decide whether the
Forecast Agent should be included in the parallel fan-out.

Returns ``'yes'`` when at least one datetime column is present in the
profile result (LangGraph routes to the forecast branch).
Returns ``'no'`` to skip forecasting (routes straight to the insight branch).

Usage in graph definition::

    graph.add_conditional_edges(
        "profiling",
        has_time_series,
        {"yes": "fan_out", "no": "fan_out"},   # both go to fan_out; fan_out uses this
    )
"""

from __future__ import annotations

from backend.orchestration.state.pipeline_state import PipelineState


def has_time_series(state: PipelineState) -> str:
    """Return 'yes' when the profiled dataset contains datetime columns.

    Reads ``state['profile_result']`` which is a ``DataProfile.to_dict()``
    dict. Checks the ``column_profiles`` list for any column with
    ``kind == 'datetime'``.

    If the profile is not yet available (e.g. profiling failed), returns
    ``'no'`` to skip forecasting safely.
    """
    profile = state.get("profile_result") or {}

    # Fast path: DataProfile exposes has_time_series directly
    if profile.get("has_time_series"):
        return "yes"

    # Fallback: inspect column_profiles list
    for col in profile.get("column_profiles", []):
        kind = col.get("kind", "unknown")
        if kind in ("datetime", "date"):
            return "yes"

    return "no"


def has_enough_numeric_columns(state: PipelineState, min_columns: int = 2) -> str:
    """Return 'yes' when enough numeric columns exist for Isolation Forest / ML.

    Used to gate the MLAgent branch in the fan-out node.
    """
    profile = state.get("profile_result") or {}
    col_prfs = profile.get("column_profiles", [])
    numeric = sum(1 for c in col_prfs if c.get("kind") == "numeric")
    return "yes" if numeric >= min_columns else "no"
