"""Socket.IO WebSocket server."""
"""Socket.IO WebSocket layer — real-time event streaming backbone.

ws_server.py:       socketio.AsyncServer; Redis psubscribe("dataset:*") bridge;
                    mounted at /ws as an ASGI sub-application.
ws_event_router.py: @register decorator + dispatch(sio, sid, event, data).
ws_handlers/:       connect, disconnect, chat, job handlers.

Room conventions (enforced here and by all agents):
    dataset:<dataset_id>           — pipeline progress; all agents; analysis.complete
    conversation:<conversation_id> — chat tokens; security/validation (private)
    monitoring:<dataset_id>        — admin perf dashboard
    job:<job_id>                   — job:status for polling clients
"""
from backend.api.websocket.ws_server       import sio, socket_app
from backend.api.websocket.ws_event_router import register, dispatch

__all__ = ["sio", "socket_app", "register", "dispatch"]
