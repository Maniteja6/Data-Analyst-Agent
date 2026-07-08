"""WebSocket connect handler."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def handle_connect(sio: Any, sid: str, environ: dict, auth: dict | None) -> None:  # noqa: ANN401
    """Handle a new Socket.IO client connection."""
    from backend.infrastructure.observability.prometheus_metrics import websocket_connections_active

    websocket_connections_active.inc()
    logger.info("ws_client_connected", sid=sid)
    await sio.emit("connected", {"status": "ok", "sid": sid}, to=sid)
