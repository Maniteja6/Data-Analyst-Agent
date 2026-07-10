# ─────────────────────────────────────────────────────────────────────────────
# frontend.Dockerfile — DataPilot React + Vite frontend
#
# Real-time design notes:
#   • nginx proxies /ws to the API container so Socket.IO works through
#     the same domain (avoids CORS issues with WebSocket upgrades)
#   • nginx proxies /api to the API container for HTTP requests
#   • gzip compression enabled for JS/CSS bundles
#   • Cache-Control: immutable for hashed assets (Vite content-hash filenames)
#   • Cache-Control: no-cache for index.html (always serve fresh HTML)
#   • WebSocket upgrade headers set explicitly for Socket.IO long-polling
#     fallback to work correctly
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Node build ───────────────────────────────────────────────────────
FROM node:20-slim AS builder

WORKDIR /app

# Install dependencies first (layer cache — only re-runs on package.json change)
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --prefer-offline

# Copy source and build
COPY frontend/ ./
ARG VITE_API_URL=/api
ARG VITE_WS_URL=/ws
ENV VITE_API_URL=${VITE_API_URL} \
    VITE_WS_URL=${VITE_WS_URL}

RUN npm run build


# ── Stage 2: nginx serving ────────────────────────────────────────────────────
FROM nginx:1.30-alpine AS production
# 1.25-alpine pinned to Alpine 3.19, EOL and no longer receiving security
# patches (Trivy CVE-2024-45491/45492 libexpat, CVE-2024-56171 libxml2 --
# all CRITICAL, all in the OS base, not our code). 1.30-alpine tracks
# Alpine 3.23, currently maintained.

LABEL description="DataPilot Frontend — React SPA served by nginx"

# The nginx:1.30-alpine tag is a frozen snapshot — Alpine security patches
# (e.g. libexpat CVEs) land in the package repo before the tag is rebuilt.
# Upgrade packages at build time so we're not stuck on whatever was current
# when the tag was last pushed.
RUN apk update && apk upgrade --no-cache && rm -rf /var/cache/apk/*

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Custom nginx config with WebSocket proxy and caching rules
COPY deploy/docker/nginx.conf /etc/nginx/conf.d/datapilot.conf

# Copy built React app
COPY --from=builder /app/dist /usr/share/nginx/html

# nginx runs as non-root on port 8080
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chmod -R 755 /usr/share/nginx/html

HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
    CMD wget -qO- http://localhost:8080/health.txt || exit 1

# Write a static health file for the HEALTHCHECK
RUN echo "ok" > /usr/share/nginx/html/health.txt

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]