"""Agent sub-package."""
"""Execution planner — LLM-generated DAG plan with fallback to static default.

PlannerAgent calls Claude Sonnet to produce an ExecutionPlan JSON.
Falls back to ExecutionPlan.create_default() on any parse or validation error.
Emits plan:ready Socket.IO event so the browser can render the pipeline topology.
"""
from backend.agents.control.planner.planner_agent import PlannerAgent
from backend.agents.control.planner.plan_schema   import (
    ExecutionPlan, TaskNode, AgentName, TaskStatus,
)

__all__ = ["PlannerAgent", "ExecutionPlan", "TaskNode", "AgentName", "TaskStatus"]
