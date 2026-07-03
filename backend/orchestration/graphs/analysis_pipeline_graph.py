"""Analysis pipeline LangGraph graph — the full batch analysis DAG.

Graph topology
--------------
              schema_node
                  │
              profiling_node
                  │
              cleaning_node ──► [has_errors → abort]
                  │
          analysis_fan_out_node    ← fires SQL, Anomaly, RAG, Forecast, ML in parallel
                  │
          analysis_fan_in_node     ← synchronises parallel branches
                  │
             insight_node
                  │
              critic_node ──► [should_retry → insight_node (max N rounds)]
                  │
              report_node
                  │
                END

Usage::

    graph = build_analysis_graph()
    result = await graph.ainvoke(initial_state)
    insight_report = result["final_report"]
"""
from __future__ import annotations

from langgraph.graph import StateGraph, END

from backend.orchestration.state.pipeline_state import PipelineState
from backend.orchestration.nodes.schema_node            import schema_node
from backend.orchestration.nodes.profiling_node         import profiling_node
from backend.orchestration.nodes.cleaning_node          import cleaning_node
from backend.orchestration.nodes.analysis_fan_out_node  import analysis_fan_out_node
from backend.orchestration.nodes.analysis_fan_in_node   import analysis_fan_in_node
from backend.orchestration.nodes.insight_node           import insight_node
from backend.orchestration.nodes.critic_node            import critic_node
from backend.orchestration.nodes.report_node            import report_node
from backend.orchestration.conditions.should_retry      import should_retry, has_errors


def build_analysis_graph() -> StateGraph:
    """Construct and compile the analysis pipeline StateGraph.

    Returns a compiled LangGraph graph ready for ``ainvoke()``.
    """
    graph = StateGraph(PipelineState)

    # ── Register nodes ────────────────────────────────────────────────────
    graph.add_node("schema",    schema_node)
    graph.add_node("profiling", profiling_node)
    graph.add_node("cleaning",  cleaning_node)
    graph.add_node("fan_out",   analysis_fan_out_node)
    graph.add_node("fan_in",    analysis_fan_in_node)
    graph.add_node("insight",   insight_node)
    graph.add_node("critic",    critic_node)
    graph.add_node("report",    report_node)

    # ── Set entry point ───────────────────────────────────────────────────
    graph.set_entry_point("schema")

    # ── Linear edges ──────────────────────────────────────────────────────
    graph.add_edge("schema",    "profiling")
    graph.add_edge("profiling", "cleaning")

    # ── Conditional edge: abort early on critical errors ──────────────────
    graph.add_conditional_edges(
        "cleaning",
        has_errors,
        {
            "abort":    END,
            "continue": "fan_out",
        },
    )

    graph.add_edge("fan_out",  "fan_in")
    graph.add_edge("fan_in",   "insight")
    graph.add_edge("insight",  "critic")

    # ── Conditional edge: retry insight if critic rejects ─────────────────
    graph.add_conditional_edges(
        "critic",
        should_retry,
        {
            "retry": "insight",
            "done":  "report",
        },
    )

    graph.add_edge("report", END)

    return graph.compile()
