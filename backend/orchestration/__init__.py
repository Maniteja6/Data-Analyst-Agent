"""LangGraph orchestration — analysis pipeline, chat query, and report generation graphs."""
"""LangGraph orchestration — typed state graphs for analysis pipeline and chat.

Sub-packages:
    state/       — LangGraph TypedDict state classes (total=False)
                    PipelineState: context, schema_result, profile_result,
                        cleaning_result, agent_results, insight_report,
                        critique, final_report,
                        errors: Annotated[list[str], operator.add]
                    ChatState: user_message, conversation_id, dataset_id,
                        messages, system_prompt, intent, sql_result,
                        rag_context, assistant_response, citations,
                        visualizations, pii_detected, injection_detected,
                        is_valid, errors: Annotated[list[str], operator.add]

    conditions/  — Edge condition functions (return string → route key)
                    has_time_series(state)             → "yes" | "no"
                    has_enough_numeric_columns(state)  → "yes" | "no"
                    should_retry(state)                → "retry" | "done"
                    has_errors(state)                  → "abort" | "continue"

    nodes/       — Async node functions (PipelineState → partial dict)
                    schema_node, profiling_node, cleaning_node
                    analysis_fan_out_node  — asyncio.create_task per agent,
                        awaits all; isolated error per agent
                    analysis_fan_in_node   — synchronisation + metadata
                    insight_node, critic_node, report_node

    graphs/      — Compiled LangGraph StateGraph instances
                    build_analysis_graph()           → analysis pipeline
                    build_chat_query_graph()         → single chat turn
                    build_report_generation_graph()  → PDF/XLSX/PPTX export

Analysis pipeline (DAG edges):
    schema ──► profiling ──► cleaning ──[has_errors]──► END
                                     └──► fan_out ──► fan_in ──► insight
                                          (parallel:                └──► critic
                                           sql, rag,              [should_retry]
                                           forecast*, ml*)          ├──► insight (retry)
                                          *conditional               └──► report ──► END

Chat query graph:
    security ──[injection]──► END
             └──► intent ──[requires_sql]──► sql ──► response ──► validation ──► END
                          └──[general]────► rag ──► response ──► validation ──► END

Real-time integration:
    Every node calls context.push_progress(pct, message, step) which emits
    job:progress to dataset:<id> Socket.IO room.
    Fan-out node fires asyncio.create_task() for each enabled agent — wall time
    equals the slowest single agent, not the sum of all agents.
"""
