"""Graph state TypedDicts."""
"""LangGraph state definitions — TypedDict schemas for each graph.

PipelineState: context, schema_result, profile_result, cleaning_result,
               agent_results, insight_report, critique, final_report,
               errors: Annotated[list[str], operator.add]

ChatState:     user_message, conversation_id, dataset_id, messages,
               system_prompt, intent, sql_result, rag_context,
               assistant_response, citations, visualizations,
               pii_detected, injection_detected, is_valid,
               errors: Annotated[list[str], operator.add]
"""
from backend.orchestration.state.pipeline_state import PipelineState
from backend.orchestration.state.chat_state     import ChatState

__all__ = ["PipelineState", "ChatState"]
