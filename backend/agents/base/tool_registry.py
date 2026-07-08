"""ToolRegistry — runtime registry for agent callable tools.

Agents register tools at construction time and invoke them by name.
Supports both synchronous and asynchronous tool functions.

Real-time integration:
    Tools that emit progress (e.g. a long-running DuckDB query) can
    accept an ``sio`` keyword argument to push Socket.IO progress events
    mid-execution without blocking the agent.

Usage::

    registry = ToolRegistry()

    @registry.tool("run_sql")
    async def run_sql_tool(sql: str, storage_key: str) -> dict:
        return await execute_query(sql, storage_key)

    # Later, inside an agent's _execute():
    result = await context.tool_registry.invoke("run_sql", sql=sql, storage_key=key)
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ToolRegistry:
    """Registry of callable tools available to agents.

    Tools are registered either via ``register()`` / ``tool()`` decorator,
    or by passing a dict to the constructor.

    Thread safety:
        The registry dict is written at construction time and read-only
        during agent execution. No locking is needed for concurrent reads.
    """

    def __init__(self, tools: dict[str, Callable] | None = None) -> None:
        self._tools: dict[str, Callable] = dict(tools or {})

    # ── Registration ──────────────────────────────────────────────────────

    def register(self, name: str, fn: Callable) -> None:
        """Register a callable under ``name``.

        Args:
            name: Tool name used in ``invoke()`` calls.
            fn:   Sync or async callable.
        """
        if name in self._tools:
            logger.warning("tool_overwritten", name=name)
        self._tools[name] = fn
        logger.debug("tool_registered", name=name, is_async=asyncio.iscoroutinefunction(fn))

    def tool(self, name: str) -> Callable:
        """Decorator that registers a function as a named tool.

        Usage::

            registry = ToolRegistry()

            @registry.tool("describe_column")
            async def describe_column(col_name: str) -> str:
                ...
        """

        def decorator(fn: Callable) -> Callable:
            self.register(name, fn)
            return fn

        return decorator

    def unregister(self, name: str) -> bool:
        """Remove a tool from the registry. Returns True if removed."""
        return self._tools.pop(name, None) is not None

    # ── Invocation ────────────────────────────────────────────────────────

    async def invoke(self, name: str, **kwargs: Any) -> Any:  # noqa: ANN401
        """Invoke a registered tool by name.

        Args:
            name:     Tool name as registered.
            **kwargs: Arguments forwarded to the tool function.

        Returns:
            The tool's return value.

        Raises:
            ValueError:  When the tool name is not registered.
            Exception:   Any exception raised by the tool itself.
        """
        fn = self._tools.get(name)
        if fn is None:
            raise ValueError(
                f"Tool '{name}' is not registered. Available tools: {self.list_tools()}"
            )

        start = time.monotonic()
        try:
            if asyncio.iscoroutinefunction(fn):
                result = await fn(**kwargs)
            else:
                result = await asyncio.get_event_loop().run_in_executor(None, lambda: fn(**kwargs))

            duration_ms = int((time.monotonic() - start) * 1000)
            logger.debug("tool_invoked", name=name, duration_ms=duration_ms)
            return result

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("tool_invocation_failed", name=name, error=str(exc))
            raise

    async def invoke_safe(self, name: str, default: Any = None, **kwargs: Any) -> Any:  # noqa: ANN401
        """Invoke a tool and return ``default`` on any exception.

        Useful inside agents where a tool failure should not abort the pipeline.
        """
        try:
            return await self.invoke(name, **kwargs)
        except Exception as exc:
            logger.warning("tool_invoke_safe_caught", name=name, error=str(exc))
            return default

    # ── Introspection ─────────────────────────────────────────────────────

    def list_tools(self) -> list[str]:
        """Return a sorted list of registered tool names."""
        return sorted(self._tools.keys())

    def has_tool(self, name: str) -> bool:
        """Return True when the named tool is registered."""
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    def __repr__(self) -> str:
        return f"ToolRegistry(tools={self.list_tools()})"


# ---------------------------------------------------------------------------
# Global default registry (shared across agents in the same process)
# ---------------------------------------------------------------------------

_DEFAULT_REGISTRY: ToolRegistry | None = None


def get_default_registry() -> ToolRegistry:
    """Return the process-level default ToolRegistry (singleton)."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = ToolRegistry()
    return _DEFAULT_REGISTRY


def reset_default_registry() -> None:
    """Reset the default registry (used in tests)."""
    global _DEFAULT_REGISTRY
    _DEFAULT_REGISTRY = None
