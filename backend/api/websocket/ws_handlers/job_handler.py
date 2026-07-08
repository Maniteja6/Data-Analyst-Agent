"""WebSocket job handler — pushes job status updates to subscribed clients."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def handle_subscribe_job(sio: Any, sid: str, data: dict) -> None:  # noqa: ANN401
    """Subscribe a client to job status updates for a specific job_id.

    The client enters the room ``job:<job_id>`` and receives ``job:progress``
    events published by Celery tasks via Redis pub/sub → Socket.IO bridge.

    Expected data: ``{job_id: str}``
    """
    job_id = data.get("job_id", "")
    if not job_id:
        await sio.emit("error", {"message": "job_id is required for job subscription"}, to=sid)
        return

    await sio.enter_room(sid, f"job:{job_id}")
    logger.debug("client_subscribed_job", sid=sid, job_id=job_id)

    # Immediately send current job status from Redis
    try:
        from backend.infrastructure.cache.redis_cache_adapter import get_redis_cache

        cache = get_redis_cache()
        status = await cache.get_job_status(job_id)
        if status:
            await sio.emit(
                "job:status",
                {
                    "job_id": job_id,
                    "status": status.get("status", "pending"),
                    "progress": status.get("progress", 0),
                    "step": status.get("step", ""),
                },
                to=sid,
            )
    except Exception as exc:
        logger.debug("job_status_fetch_failed", job_id=job_id, error=str(exc))
