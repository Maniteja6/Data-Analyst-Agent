"""FastAPI routers — all mounted under /api/v1.

health_router         GET /health, GET /ready
datasets_router       POST /datasets/upload, GET /:id, GET /, DELETE /:id
insights_router       GET /insights/:dataset_id
conversations_router  POST /, GET /:id, POST /:id/messages
exports_router        POST /exports/:dataset_id  → 202 + job_id
jobs_router           GET /jobs/:job_id          → Redis hash
"""

from backend.api.routers.conversations import router as conversations_router
from backend.api.routers.datasets import router as datasets_router
from backend.api.routers.exports import router as exports_router
from backend.api.routers.health import router as health_router
from backend.api.routers.insights import router as insights_router
from backend.api.routers.jobs import router as jobs_router

__all__ = [
    "health_router",
    "datasets_router",
    "insights_router",
    "conversations_router",
    "exports_router",
    "jobs_router",
]
