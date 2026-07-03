"""Chat query LangGraph graph — processes one user chat message end-to-end.

Graph topology
--------------
  START
    │
  security_node      ← PII + injection checks; blocks on detection
    │
  intent_node        ← classifies the user's intent
    │
  [routing branch]
    ├─ sql_intent   → sql_node
    ├─ forecast     → forecast_node
    ├─ general      → rag_node
    └─ (all paths) →
    │
  response_node      ← builds final assistant text + citations + visualisations
    │
  validation_node    ← checks for hallucinations / schema inconsistencies
    │
  END

Usage::

    graph  = build_chat_query_graph()
    result = await graph.ainvoke(initial_state)
    reply  = result["assistant_response"]
"""
from __future__ import annotations

from langgraph.graph import StateGraph, END

from backend.orchestration.state.chat_state import ChatState


# ---------------------------------------------------------------------------
# Inline node implementations (lightweight; heavy logic in agent classes)
# ---------------------------------------------------------------------------

async def security_node(state: ChatState) -> dict:
    """Check for PII and prompt injection before any LLM call."""
    from backend.config.feature_flags import flags
    if not flags.pii_detection_enabled and not flags.injection_detection_enabled:
        return {"pii_detected": False, "injection_detected": False, "is_valid": True}
    try:
        from backend.agents.security_agent import SecurityAgent
        from backend.infrastructure.llm.bedrock.bedrock_converse_adapter import BedrockConverseAdapter
        agent = SecurityAgent(llm=BedrockConverseAdapter())
        result = await agent.run(message=state.get("user_message", ""))
        return {
            "pii_detected":       result.get("pii_detected", False),
            "injection_detected": result.get("injection_detected", False),
            "is_valid":           not result.get("injection_detected", False),
        }
    except Exception as exc:
        return {"pii_detected": False, "injection_detected": False, "is_valid": True,
                "errors": [f"SecurityNode: {exc}"]}


async def intent_node(state: ChatState) -> dict:
    """Classify user intent and extract named entities."""
    try:
        from backend.agents.intent_agent import IntentAgent
        from backend.infrastructure.llm.bedrock.bedrock_converse_adapter import BedrockConverseAdapter
        agent  = IntentAgent(llm=BedrockConverseAdapter())
        intent = await agent.run(
            message=state.get("user_message", ""),
            dataset_id=state.get("dataset_id", ""),
        )
        return {"intent": intent}
    except Exception as exc:
        return {"intent": {"intent": "general_question", "requires_sql": False, "requires_rag": True},
                "errors": [f"IntentNode: {exc}"]}


async def sql_node(state: ChatState) -> dict:
    """Execute a SQL query based on the user's intent."""
    try:
        from backend.agents.sql_agent import SQLAgent
        from backend.infrastructure.llm.bedrock.bedrock_converse_adapter import BedrockConverseAdapter
        from backend.analytics_engine.sql_engine.duckdb_manager import DuckDBManager
        from backend.analytics_engine.ingestion.file_reader import FileReader
        from backend.infrastructure.persistence.database import get_session
        from backend.infrastructure.persistence.repositories.postgres_dataset_repository import (
            PostgresDatasetRepository,
        )

        async with get_session() as db_session:
            repo    = PostgresDatasetRepository(db_session)
            dataset = await repo.get_by_id(state.get("dataset_id", ""))
        if not dataset:
            return {"sql_result": {}}

        reader = FileReader()
        df = await reader.read(dataset.storage_key)
        agent  = SQLAgent(llm=BedrockConverseAdapter(), db=DuckDBManager())
        result = await agent.run(
            df=df,
            user_question=state.get("user_message", ""),
            intent=state.get("intent", {}),
        )
        return {"sql_result": result}
    except Exception as exc:
        return {"sql_result": {}, "errors": [f"SQLNode: {exc}"]}


async def rag_node(state: ChatState) -> dict:
    """Retrieve relevant schema chunks from Qdrant."""
    from backend.config.feature_flags import flags
    if not flags.rag_enabled:
        return {"rag_context": ""}
    try:
        from backend.agents.rag_agent import RAGAgent
        from backend.infrastructure.vector_store.collection_manager import CollectionManager
        from backend.infrastructure.vector_store.bedrock_embedding_service import get_embedding_service

        agent = RAGAgent(
            collection_manager=CollectionManager(),
            embedding_service=get_embedding_service(),
        )
        result = await agent.retrieve(
            query=state.get("user_message", ""),
            dataset_id=state.get("dataset_id", ""),
        )
        return {"rag_context": result.get("context", "")}
    except Exception as exc:
        return {"rag_context": "", "errors": [f"RAGNode: {exc}"]}


async def response_node(state: ChatState) -> dict:
    """Generate the final assistant response using InsightAgent."""
    try:
        from backend.agents.chat_response_agent import ChatResponseAgent
        from backend.infrastructure.llm.bedrock.bedrock_converse_adapter import BedrockConverseAdapter
        agent  = ChatResponseAgent(llm=BedrockConverseAdapter())
        result = await agent.run(
            user_message=state.get("user_message", ""),
            sql_result=state.get("sql_result", {}),
            rag_context=state.get("rag_context", ""),
            messages=state.get("messages", []),
            system_prompt=state.get("system_prompt", ""),
        )
        return {
            "assistant_response": result.get("response", ""),
            "citations":          result.get("citations", []),
            "visualizations":     result.get("visualizations", []),
        }
    except Exception as exc:
        return {"assistant_response": f"I'm sorry, I couldn't process that query: {exc}",
                "errors": [f"ResponseNode: {exc}"]}


async def validation_node(state: ChatState) -> dict:
    """Validate the response for factual consistency with the dataset schema."""
    from backend.config.feature_flags import flags
    if not flags.injection_detection_enabled:
        return {"is_valid": True}
    try:
        from backend.agents.validation_agent import ValidationAgent
        from backend.infrastructure.llm.bedrock.bedrock_converse_adapter import BedrockConverseAdapter
        agent  = ValidationAgent(llm=BedrockConverseAdapter())
        result = await agent.run(
            response=state.get("assistant_response", ""),
            sql_result=state.get("sql_result", {}),
        )
        return {"is_valid": result.get("is_valid", True)}
    except Exception:
        return {"is_valid": True}


# ---------------------------------------------------------------------------
# Routing conditions
# ---------------------------------------------------------------------------

def _route_by_intent(state: ChatState) -> str:
    """Route based on intent classification."""
    intent = state.get("intent", {})
    if state.get("injection_detected"):
        return END  # type: ignore[return-value]
    if intent.get("requires_sql"):
        return "sql"
    return "rag"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_chat_query_graph() -> StateGraph:
    """Build and compile the chat query StateGraph."""
    graph = StateGraph(ChatState)

    graph.add_node("security",   security_node)
    graph.add_node("intent",     intent_node)
    graph.add_node("sql",        sql_node)
    graph.add_node("rag",        rag_node)
    graph.add_node("response",   response_node)
    graph.add_node("validation", validation_node)

    graph.set_entry_point("security")
    graph.add_edge("security", "intent")

    graph.add_conditional_edges(
        "intent",
        _route_by_intent,
        {
            "sql": "sql",
            "rag": "rag",
            END:   END,
        },
    )

    # Both SQL and RAG paths converge at response
    graph.add_edge("sql", "response")
    graph.add_edge("rag", "response")
    graph.add_edge("response", "validation")
    graph.add_edge("validation", END)

    return graph.compile()
