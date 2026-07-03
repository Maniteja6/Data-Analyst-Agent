"""WebSocket event router — maps event type strings to handler coroutines."""
from __future__ import annotations

from typing import Any, Callable, Awaitable

import structlog

logger = structlog.get_logger(__name__)

# Registry: event_type → async handler
_HANDLERS: dict[str, Callable] = {}


def register(event_type: str):
    """Decorator to register a WebSocket event handler."""
    def decorator(fn: Callable) -> Callable:
        _HANDLERS[event_type] = fn
        return fn
    return decorator


async def dispatch(sio, sid: str, event_type: str, data: dict) -> None:
    """Dispatch an incoming Socket.IO event to the registered handler."""
    handler = _HANDLERS.get(event_type)
    if handler is None:
        logger.warning("ws_unknown_event_type", event_type=event_type, sid=sid)
        await sio.emit("error", {"message": f"Unknown event: {event_type}"}, to=sid)
        return
    try:
        await handler(sio, sid, data)
    except Exception as exc:
        logger.error("ws_handler_error", event_type=event_type, sid=sid, error=str(exc))
        await sio.emit("error", {"message": "Internal error processing event."}, to=sid)
