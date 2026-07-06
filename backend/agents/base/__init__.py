"""Agent sub-package."""
"""Base agent primitives — shared by all 19 agents.

Exports:
    BaseAgent       — abstract async agent with 3-attempt retry + OTel span
    AgentContext    — shared mutable pipeline state; Socket.IO push helpers
    AgentResult     — typed result envelope with token counts + cost estimate
    ToolRegistry    — register/invoke named sync or async tool functions
"""
from backend.agents.base.base_agent    import BaseAgent
from backend.agents.base.agent_context import AgentContext
from backend.agents.base.agent_result  import AgentResult
from backend.agents.base.tool_registry import ToolRegistry

__all__ = ["BaseAgent", "AgentContext", "AgentResult", "ToolRegistry"]
