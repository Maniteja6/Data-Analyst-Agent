"""Compiled LangGraph StateGraph instances — one per workflow.

build_analysis_graph():
    schema → profiling → cleaning → fan_out → fan_in → insight
    → critic [should_retry] → report → END

build_chat_query_graph():
    security → intent → [sql | rag] → response → validation → END

build_report_generation_graph():
    load_report → render → upload → END
"""

from backend.orchestration.graphs.analysis_pipeline_graph import build_analysis_graph
from backend.orchestration.graphs.chat_query_graph import build_chat_query_graph
from backend.orchestration.graphs.report_generation_graph import build_report_generation_graph

__all__ = [
    "build_analysis_graph",
    "build_chat_query_graph",
    "build_report_generation_graph",
]
