# ============================================================================
# Forensic Council — Developer Makefile
# ============================================================================
# Convenience targets for common development operations.
# All docker commands reference the canonical docker/ directory.
#
# Usage:
#   make infra        — Start databases only (Redis, Postgres, Qdrant)
#   make up           — Full stack in Docker (build + start all services)
#   make down         — Stop all containers
#   make logs         — Tail all container logs
#   make backend      — Run backend natively (hot reload)
#   make frontend     — Run frontend natively (hot reload)
#   make test         — Run backend tests
#   make lint         — Lint frontend
#   make clean        — Remove all Docker volumes (destructive!)
# ============================================================================

COMPOSE     = docker compose -f docker/docker-compose.yml --env-file .env
INFRA       = docker compose -f docker/docker-compose.infra.yml --env-file .env
PROD        = docker compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml --env-file .env

.PHONY: help infra up down logs backend frontend test lint clean rebuild env-check

help:
	@echo "Forensic Council — available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

env-check: ## Check required env files exist
	@test -f .env || (echo "ERROR: .env missing — run: cp .env.example .env" && exit 1)
	@test -f backend/.env || (echo "ERROR: backend/.env missing — run: cp backend/.env.example backend/.env" && exit 1)
	@echo "✅  .env files present"

infra: env-check ## Start infrastructure containers (Redis, Postgres, Qdrant) only
	$(INFRA) up -d
	@echo "✅  Infra running — Redis :6379 | Postgres :5432 | Qdrant :6333"

up: env-check ## Build and start the full stack in Docker
	$(COMPOSE) up --build -d
	@echo "✅  Stack running — Frontend :3000 | API :8000"

down: ## Stop all containers
	$(COMPOSE) down

prod: env-check ## Start production stack (no debug, no hot reload)
	$(PROD) up --build -d

logs: ## Tail logs for all containers
	$(COMPOSE) logs -f

backend: env-check ## Run backend natively with hot reload (requires infra running)
	cd backend && uv run uvicorn api.main:app --reload --port 8000

frontend: ## Run frontend natively with hot reload
	cd frontend && npm run dev

test: ## Run backend test suite
	cd backend && uv run pytest tests/ -v

lint: ## Lint frontend TypeScript
	cd frontend && npm run lint

type-check: ## TypeScript type-check frontend
	cd frontend && npm run type-check

rebuild: env-check ## Force rebuild all Docker images from scratch
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d

clean: ## DESTRUCTIVE: Remove all Docker volumes (wipes DB data)
	@read -p "⚠️  This will delete ALL database volumes. Confirm? [y/N] " yn; \
	if [ "$$yn" = "y" ] || [ "$$yn" = "Y" ]; then \
		$(COMPOSE) down -v; echo "✅  Volumes removed."; \
	else \
		echo "Aborted."; \
	fi

init-keys: ## Generate new ECDSA keys for all agents (dev only)
	cd backend && uv run python scripts/init_db.py

smoke: ## Run backend smoke test against a running instance
	bash backend/scripts/smoke_test.sh
