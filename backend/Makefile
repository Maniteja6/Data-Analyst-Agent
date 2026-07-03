# ===========================================================================
# DataPilot Backend — Makefile
# Usage: make <target>
# ===========================================================================

.PHONY: help install dev lint format typecheck test test-unit \
        test-integration test-e2e evals coverage \
        migrate migrate-new migrate-history migrate-downgrade \
        run worker worker-beat \
        docker-up docker-down clean

# ── Defaults ────────────────────────────────────────────────────────────────
PYTHON       ?= python3
PIP          ?= pip
APP_MODULE   := backend.api.main:app
WORKER_APP   := backend.infrastructure.job_queue.celery_app
COVERAGE_MIN := 70

help:            ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── Installation ─────────────────────────────────────────────────────────────
install:         ## Install production + dev dependencies
	$(PIP) install -e ".[dev]" --break-system-packages

install-prod:    ## Install production dependencies only
	$(PIP) install -e "." --break-system-packages

# ── Development server ───────────────────────────────────────────────────────
dev:             ## Start FastAPI dev server with hot-reload
	uvicorn $(APP_MODULE) \
	  --host 0.0.0.0 --port 8000 \
	  --reload --reload-dir backend \
	  --log-level debug

run:             ## Start FastAPI production server
	uvicorn $(APP_MODULE) \
	  --host 0.0.0.0 --port 8000 \
	  --workers 4 --loop uvloop

# ── Lint / format / typecheck ────────────────────────────────────────────────
lint:            ## Run ruff linter
	ruff check backend/

format:          ## Auto-fix ruff violations and format
	ruff check --fix backend/
	ruff format backend/

typecheck:       ## Run mypy type checker
	mypy backend/ --ignore-missing-imports --no-error-summary

# ── Tests ────────────────────────────────────────────────────────────────────
test:            ## Run all tests
	pytest -v --tb=short

test-unit:       ## Run unit tests only
	pytest backend/tests/unit/ -v --tb=short

test-integration: ## Run integration tests (requires running infra)
	pytest backend/tests/integration/ -v --tb=short

test-e2e:        ## Run end-to-end tests (requires full stack)
	pytest backend/tests/e2e/ -v --tb=short -s

evals:           ## Run agent evaluation suite
	$(PYTHON) -m backend.tests.evals.eval_runner

coverage:        ## Run tests with coverage report
	pytest --cov=backend --cov-report=term-missing \
	  --cov-fail-under=$(COVERAGE_MIN) \
	  --cov-report=html:htmlcov/
	@echo "HTML report: htmlcov/index.html"

# ── Database migrations ───────────────────────────────────────────────────────
migrate:         ## Apply all pending Alembic migrations
	alembic upgrade head

migrate-new:     ## Create a new auto-generated migration (set msg=... )
	@test -n "$(msg)" || (echo "Usage: make migrate-new msg='add users table'" && exit 1)
	alembic revision --autogenerate -m "$(msg)"

migrate-history: ## Show migration history
	alembic history --verbose

migrate-downgrade: ## Roll back one migration
	alembic downgrade -1

migrate-reset:   ## WARNING: drops all tables and re-applies migrations (dev only)
	@echo "⚠️  This will destroy all data. Press Ctrl-C to abort..."
	@sleep 3
	alembic downgrade base
	alembic upgrade head

# ── Celery workers ───────────────────────────────────────────────────────────
worker:          ## Start Celery worker (analysis + agents + reports queues)
	celery -A $(WORKER_APP) worker \
	  --loglevel=info \
	  --queues=celery,analysis,agents,reports \
	  --concurrency=4 \
	  --hostname=worker@%h

worker-beat:     ## Start Celery beat scheduler (periodic tasks)
	celery -A $(WORKER_APP) beat --loglevel=info

worker-flower:   ## Start Flower monitoring dashboard (port 5555)
	celery -A $(WORKER_APP) flower --port=5555

# ── Local infrastructure ──────────────────────────────────────────────────────
docker-up:       ## Start local infra (PostgreSQL, Redis, MinIO, Qdrant, Kafka)
	docker compose -f ../../deploy/docker/docker-compose.dev.yml up -d
	@echo "Waiting for services to be ready..."
	@sleep 5
	$(MAKE) migrate

docker-down:     ## Stop local infra
	docker compose -f ../../deploy/docker/docker-compose.dev.yml down

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:           ## Remove build artefacts, caches, coverage reports
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc"     -delete 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov"   -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "Clean done."
