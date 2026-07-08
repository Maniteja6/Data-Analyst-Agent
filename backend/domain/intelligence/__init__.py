"""Intelligence bounded context — owns the AI agent execution model.

Aggregate:  ExecutionPlan (tasks DAG; emits plan:ready Socket.IO payload)
Entity:     TaskNode (status state machine: pending→running→succeeded|failed|skipped)
VOs:        LLMResponse (as_json, as_sql, estimated_cost_usd, was_truncated)
            IntentClassification (routing flags: requires_sql/rag/forecast/viz)
"""

from backend.domain.intelligence.entities.execution_plan import ExecutionPlan
from backend.domain.intelligence.entities.task_node import TaskNode
from backend.domain.intelligence.value_objects.llm_response import LLMResponse

__all__ = ["ExecutionPlan", "TaskNode", "LLMResponse"]
