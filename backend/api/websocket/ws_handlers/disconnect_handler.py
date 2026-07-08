"""WebSocket disconnect handler."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def handle_disconnect(sio: Any, sid: str) -> None:  # noqa: ANN401
    """Handle a Socket.IO client disconnection."""
    from backend.infrastructure.observability.prometheus_metrics import websocket_connections_active

    websocket_connections_active.dec()
    logger.info("ws_client_disconnected", sid=sid)
