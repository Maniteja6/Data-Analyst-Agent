# ─────────────────────────────────────────────────────────────────────────────
# analytics.Dockerfile — DataPilot analytics engine
#
# Runs the deterministic pipeline (ingest → profile → clean → anomaly)
# as a standalone Celery worker on the `analysis` queue only.
#
# Separated from the main worker image so it can be scaled on CPU-optimised
# instances (c6i.2xlarge) while agent workers run on memory-optimised nodes.
#
# Real-time design notes:
#   • polars is the primary DataFrame library (10x faster than pandas for
#     profiling wide datasets — critical for per-column Socket.IO events)
#   • DuckDB runs in-process for SQL queries (no separate DuckDB server)
#   • scikit-learn, prophet, statsforecast, xgboost installed for ML/forecast
#   • numba NOT included — install separately if needed for custom statistics
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM python:3.11-slim AS deps

WORKDIR /deps

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libgomp1 \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-analytics.txt* ./

# Upgrade pip's own build tooling first — some transitive sdists get built
# via pip's isolated build environments, which otherwise bootstrap whatever
# old setuptools/wheel/jaraco.context happens to be cached (Trivy flagged
# CVEs in both: wheel <0.46.2, jaraco.context <6.1.0).
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

RUN pip install --no-cache-dir --prefix=/install \
    polars \
    duckdb \
    pyarrow \
    scikit-learn \
    prophet \
    statsforecast \
    xgboost \
    scipy \
    -r requirements.txt \
    $(test -f requirements-analytics.txt && echo "-r requirements-analytics.txt" || true)


# ── Stage 2: production ───────────────────────────────────────────────────────
FROM python:3.11-slim AS production

LABEL description="DataPilot Analytics Engine — profiling, cleaning, anomaly detection"

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

# OMP_NUM_THREADS=2: limit per-task OpenMP threads so 4 Celery workers
# don't over-subscribe cores (4 workers × 2 threads = 8 = vCPU count)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    OMP_NUM_THREADS=2

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD celery -A backend.infrastructure.job_queue.celery_app inspect ping \
        --destination celery@${HOSTNAME} || exit 1

CMD ["celery", "-A", "backend.infrastructure.job_queue.celery_app", "worker", \
     "--queues=analysis", \
     "--concurrency=4", \
     "--loglevel=info", \
     "--without-gossip", \
     "--without-mingle", \
     "-Ofair"]