"""Socket.IO server — real-time WebSocket server for DataPilot.

Uses ``python-socketio`` with the ``asyncio`` transport so it integrates
seamlessly with the FastAPI event loop. The Socket.IO app is mounted on
the FastAPI ASGI app as a sub-application at ``/ws``.

Rooms (Socket.IO concept):
  - ``dataset:<dataset_id>``  — all clients watching one dataset's progress
  - ``conversation:<id>``     — clients in a specific chat conversation

Redis pub/sub bridge:
  The analytics pipeline workers publish JSON events to Redis channels
  (``dataset:<dataset_id>``). A background asyncio task subscribes to Redis
  and re-emits each event as a Socket.IO event to the appropriate room.
  This decouples the workers from the WebSocket server.
"""
from __future__ import annotations

import asyncio
import json

import socketio
import structlog

logger = structlog.get_logger(__name__)

# Create async Socket.IO server
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",  # narrowed by FastAPI CORS middleware
    logger=False,
    engineio_logger=False,
)

# ASGI app wrapping the Socket.IO server (mounted at /ws in main.py)
socket_app = socketio.ASGIApp(sio, socketio_path="")

# Active dataset room subscriptions: dataset_id → set of client SIDs
_dataset_rooms: dict[str, set[str]] = {}

# Background Redis subscriber task
_redis_subscriber_task: asyncio.Task | None = None


# ---------------------------------------------------------------------------
# Socket.IO event handlers (delegated to ws_handlers/)
# ---------------------------------------------------------------------------

@sio.on("connect")
async def on_connect(sid: str, environ: dict, auth: dict | None = None) -> None:
    from backend.api.websocket.ws_handlers.connect_handler import handle_connect
    await handle_connect(sio, sid, environ, auth)


@sio.on("disconnect")
async def on_disconnect(sid: str) -> None:
    from backend.api.websocket.ws_handlers.disconnect_handler import handle_disconnect
    await handle_disconnect(sio, sid)


@sio.on("subscribe_dataset")
async def on_subscribe_dataset(sid: str, data: dict) -> None:
    """Client subscribes to progress updates for a dataset."""
    dataset_id = data.get("dataset_id", "")
    if dataset_id:
        await sio.enter_room(sid, f"dataset:{dataset_id}")
        _dataset_rooms.setdefault(dataset_id, set()).add(sid)
        logger.debug("client_subscribed_dataset", sid=sid, dataset_id=dataset_id)
        await sio.emit("subscribed", {"dataset_id": dataset_id}, to=sid)


@sio.on("unsubscribe_dataset")
async def on_unsubscribe_dataset(sid: str, data: dict) -> None:
    dataset_id = data.get("dataset_id", "")
    if dataset_id:
        await sio.leave_room(sid, f"dataset:{dataset_id}")
        _dataset_rooms.get(dataset_id, set()).discard(sid)


@sio.on("chat_message")
async def on_chat_message(sid: str, data: dict) -> None:
    from backend.api.websocket.ws_handlers.chat_handler import handle_chat_message
    await handle_chat_message(sio, sid, data)


@sio.on("subscribe_job")
async def on_subscribe_job(sid: str, data: dict) -> None:
    from backend.api.websocket.ws_handlers.job_handler import handle_subscribe_job
    await handle_subscribe_job(sio, sid, data)


# ---------------------------------------------------------------------------
# Redis → Socket.IO bridge
# ---------------------------------------------------------------------------

async def start_redis_subscriber() -> None:
    """Start a background task that listens to Redis pub/sub and forwards events."""
    global _redis_subscriber_task
    if _redis_subscriber_task and not _redis_subscriber_task.done():
        return
    _redis_subscriber_task = asyncio.create_task(_redis_bridge_loop())
    logger.info("redis_socketio_bridge_started")


async def _redis_bridge_loop() -> None:
    """Subscribe to all DataPilot Redis channels and re-emit via Socket.IO."""
    try:
        import redis.asyncio as aioredis
        from backend.config.settings import get_settings
        settings = get_settings()
        client   = aioredis.from_url(settings.redis_url, decode_responses=True)
        pubsub   = client.pubsub()

        # Subscribe to the pattern channel
        await pubsub.psubscribe("dataset:*")
        logger.info("redis_pubsub_subscribed", pattern="dataset:*")

        async for message in pubsub.listen():
            if message["type"] not in ("pmessage", "message"):
                continue
            try:
                channel = message.get("channel", "")
                payload = json.loads(message.get("data", "{}"))
                event_type = payload.get("type", "update")

                # Forward to the matching Socket.IO room
                await sio.emit(event_type, payload, room=channel)

            except Exception as exc:
                logger.warning("redis_bridge_error", error=str(exc))

    except asyncio.CancelledError:
        logger.info("redis_bridge_cancelled")
    except Exception as exc:
        logger.error("redis_bridge_failed", error=str(exc))
