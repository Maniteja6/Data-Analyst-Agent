# ─────────────────────────────────────────────────────────────────────────────
# Dockerfile.api — DataPilot FastAPI + Socket.IO real-time API server
#
# Real-time design notes:
#   • uvicorn runs with --loop uvloop for maximum asyncio throughput
#   • gevent is NOT used — Socket.IO uses the asyncio adapter (not eventlet)
#   • aioredis is installed for the Redis pub/sub bridge (psubscribe loop)
#   • aiokafka is installed for the domain event consumers (asyncio tasks)
#   • Port 8000: FastAPI HTTP + Socket.IO ASGI (mounted at /ws)
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: dependency resolver ─────────────────────────────────────────────
FROM python:3.11-slim AS deps

WORKDIR /deps

# System build tools needed for some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-api.txt* ./

# Install into a prefix so we can copy it cleanly
RUN pip install --no-cache-dir --prefix=/install \
    -r requirements.txt \
    $(test -f requirements-api.txt && echo "-r requirements-api.txt" || true)


# ── Stage 2: production image ─────────────────────────────────────────────────
FROM python:3.11-slim AS production

LABEL maintainer="DataPilot <platform@datapilot.ai>"
LABEL description="DataPilot API — FastAPI + Socket.IO real-time server"

# Runtime-only system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN groupadd --gid 1001 datapilot && \
    useradd --uid 1001 --gid datapilot --shell /bin/bash --create-home datapilot

# Copy installed Python packages from deps stage
COPY --from=deps /install /usr/local

WORKDIR /app

# Copy application code
COPY backend/ ./backend/
COPY alembic.ini ./

# Ensure correct ownership
RUN chown -R datapilot:datapilot /app

USER datapilot

# Health check — hits the /health endpoint
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# uvicorn flags:
#   --loop uvloop         — fastest asyncio event loop (C extension)
#   --ws websockets       — websockets library for Socket.IO transport
#   --timeout-keep-alive  — keep connections alive for streaming responses
#   --access-log          — structured access log to stdout
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

CMD ["uvicorn", "backend.api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--loop", "uvloop", \
     "--ws", "websockets", \
     "--timeout-keep-alive", "75", \
     "--access-log", \
     "--log-level", "info"]