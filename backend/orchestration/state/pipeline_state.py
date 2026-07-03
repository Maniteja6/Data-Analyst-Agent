"""PipelineState — shared state for the analysis pipeline LangGraph graph.

LangGraph passes state between nodes as a TypedDict. Every node receives the
full state, reads the fields it needs, and returns a partial dict of the fields
it updates. LangGraph merges the partial update into the running state using
the configured ``reducer`` (default: last-write-wins for most fields,
``operator.add`` for list fields that accumulate across parallel branches).

State fields
------------
context:         Routing metadata set at graph entry: dataset_id, session_id,
                 storage_key, schema, correlation_id.
schema_result:   Output of the SchemaNode (column type classifications).
profile_result:  Output of the ProfilingNode (DataProfile entity dict).
cleaning_result: Output of the CleaningNode (cleaned data reference + CleaningReport).
agent_results:   Dict mapping agent_name → result payload. Each parallel
                 analysis agent writes its output here after the fan-out.
insight_report:  Dict produced by the InsightNode from all agent_results.
critique:        Structured critique from the CriticNode.
final_report:    The complete serialised InsightReport dict after all passes.
errors:          List of error strings accumulated across nodes (never overwrites).
metadata:        Free-form dict for timing, token counts, cost summaries.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict


class PipelineState(TypedDict, total=False):
    """Mutable state flowing through the analysis pipeline graph.

    ``total=False`` means all fields are optional — nodes only set the
    fields they produce, and downstream nodes check for ``None`` before using them.

    The ``errors`` field uses ``operator.add`` as its LangGraph reducer so
    that multiple parallel branches can all append errors without overwriting
    each other's contributions.
    """

    # ── Routing / identity ────────────────────────────────────────────────
    context: dict[str, Any]
    """Entry-point metadata: {dataset_id, session_id, storage_key, schema, correlation_id}."""

    # ── Pipeline stage outputs ────────────────────────────────────────────
    schema_result:   dict[str, Any]
    """ColumnSchema list as produced by the SchemaAgent."""

    profile_result:  dict[str, Any]
    """DataProfile.to_dict() output from DataProfiler."""

    cleaning_result: dict[str, Any]
    """{'cleaned_storage_key': str, 'cleaning_report': dict}."""

    agent_results:   dict[str, Any]
    """agent_name → result payload, populated by parallel analysis agents."""

    insight_report:  dict[str, Any]
    """Serialised InsightReport.to_dict() output from InsightNode."""

    critique:        dict[str, Any]
    """CriticNode output: {'approved': bool, 'issues': list[str], 'revised_insights': list}."""

    final_report:    dict[str, Any]
    """Complete serialised report after ReportNode processing."""

    # ── Accumulating fields (LangGraph add-reducer) ───────────────────────
    errors: Annotated[list[str], operator.add]
    """Error messages from any node — accumulated via operator.add."""

    # ── Diagnostics ───────────────────────────────────────────────────────
    metadata: dict[str, Any]
    """Timing, token counts, cost. Merged by nodes via dict update."""
