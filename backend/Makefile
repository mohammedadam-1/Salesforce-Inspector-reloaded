# ─────────────────────────────────────────────
# SFIR Backend — Makefile
# ─────────────────────────────────────────────

.PHONY: help install dev-install lint typecheck test test-cov migrate alembic-autogen docker-up docker-down clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies
	uv sync --no-dev

dev-install: ## Install all dependencies including dev
	uv sync

lint: ## Run Ruff linter
	uv run ruff check src/ tests/

lint-fix: ## Run Ruff linter with auto-fix
	uv run ruff check --fix src/ tests/

typecheck: ## Run MyPy type checker
	uv run mypy src/

test: ## Run all tests
	uv run pytest -v

test-cov: ## Run tests with coverage
	uv run pytest --cov=sfir_backend --cov-report=term-missing

test-unit: ## Run unit tests only
	uv run pytest -v -m "unit" tests/unit/

test-int: ## Run integration tests only (requires DB)
	uv run pytest -v -m "integration" tests/integration/

migrate: ## Run Alembic migrations
	uv run alembic upgrade head

alembic-autogen: ## Generate a new Alembic migration
	uv run alembic revision --autogenerate -m "$(name)"

docker-up: ## Start full stack with Docker Compose
	docker compose up -d

docker-up-infra: ## Start only infrastructure (DB, Redis)
	docker compose -f docker-compose.infra.yml up -d

docker-down: ## Stop all Docker containers
	docker compose down

docker-logs: ## Follow logs
	docker compose logs -f

clean: ## Clean Python cache files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
