# ─────────────────────────────────────────────────────────────────────────────
# worker.Dockerfile — DataPilot Celery workers
#
# Three queues with separate concurrency settings:
#   analysis  (-c 4)  CPU-bound: DataProfiler, DataCleaner, AnomalyDetector
#   agents    (-c 2)  I/O-bound: LangGraph + Bedrock API calls
#   reports   (-c 1)  Disk-bound: PDF/XLSX/PPTX render + S3 upload
#
# Real-time design notes:
#   • Each queue is a separate Docker service in docker-compose so they
#     can be scaled independently (agents queue needs more RAM for LangGraph)
#   • QUEUE env var selects which queue this container runs
#   • prophet, statsforecast, xgboost, reportlab, openpyxl, python-pptx
#     all installed here — NOT in the API image (keeps API image small)
#   • libgomp is required for XGBoost multi-threading on Linux
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: dependency resolver ─────────────────────────────────────────────
FROM python:3.11-slim AS deps

WORKDIR /deps

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-worker.txt* ./

RUN pip install --no-cache-dir --prefix=/install \
    -r requirements.txt \
    $(test -f requirements-worker.txt && echo "-r requirements-worker.txt" || true)


# ── Stage 2: production image ─────────────────────────────────────────────────
FROM python:3.11-slim AS production

LABEL description="DataPilot Worker — Celery analytics + agent + report queues"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1001 datapilot && \
    useradd --uid 1001 --gid datapilot --shell /bin/bash --create-home datapilot

COPY --from=deps /install /usr/local

WORKDIR /app
COPY backend/ ./backend/

RUN chown -R datapilot:datapilot /app

USER datapilot

# QUEUE controls which Celery queue this container processes.
# Set via environment variable in docker-compose (analysis | agents | reports).
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    QUEUE=analysis \
    CONCURRENCY=4

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD celery -A backend.infrastructure.job_queue.celery_app inspect ping \
        --destination celery@${HOSTNAME} || exit 1

# Entrypoint selects concurrency by queue type:
#   analysis: 4 (CPU-bound profiling/cleaning)
#   agents:   2 (I/O-bound Bedrock calls — keep low to avoid throttling)
#   reports:  1 (disk-bound rendering — single threaded per worker)
CMD celery -A backend.infrastructure.job_queue.celery_app worker \
    --queues=${QUEUE} \
    --concurrency=${CONCURRENCY} \
    --loglevel=info \
    --without-gossip \
    --without-mingle \
    --without-heartbeat \
    -Ofair