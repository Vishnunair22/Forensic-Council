# ============================================================================
# Forensic Council — Makefile  (v1.0.0)
# ============================================================================
# Requires: Docker 23+ (BuildKit enabled by default) or set DOCKER_BUILDKIT=1
#
# SHARED MODEL VOLUMES: All targets use the same project name ("forensic-council")
# which is also set in .env via COMPOSE_PROJECT_NAME. This ensures dev and prod
# builds share the same named volumes — ML models are NEVER downloaded twice.
#
# Usage:
#   make up          → build (if needed) and start all services
#   make dev         → start with hot-reload
#   make cache-status → show ML model cache state without starting anything
#   make rebuild     → smart rebuild (skips layers where source hasn't changed)
#   make rebuild-backend  → rebuild only the backend
#   make rebuild-frontend → rebuild only the frontend
#   make down        → stop services, KEEP volumes (models preserved ✅)
#   make down-clean  → stop services, DELETE volumes (models wiped ⚠️)
# ============================================================================

COMPOSE       = docker compose -f docs/docker/docker-compose.yml --env-file .env
COMPOSE_DEV   = $(COMPOSE) -f docs/docker/docker-compose.dev.yml
COMPOSE_PROD  = $(COMPOSE) -f docs/docker/docker-compose.prod.yml
PROJECT_NAME  = forensic-council

.PHONY: up dev infra build rebuild rebuild-backend rebuild-frontend \
        down down-clean logs ps prod prune \
        cache-status cache-warm check-env

# ─── Primary targets ──────────────────────────────────────────────────────────

## Build (if needed) and start all services in background
up: check-env
	$(COMPOSE) up --build -d
	@echo ""
	@echo "✅  Services started. Frontend → http://localhost:3000"
	@echo "✅  Backend API   → http://localhost:8000"
	@echo ""

## Start in development mode (hot-reload for backend and frontend)
dev: check-env
	$(COMPOSE_DEV) up --build
	@echo ""

## Start only infrastructure (redis, postgres, qdrant) — for native dev
infra:
	docker compose -f docs/docker/docker-compose.infra.yml --env-file .env up -d
	@echo "✅  Infrastructure started (Redis, Postgres, Qdrant)"

## Build images only (no start)
build: check-env
	$(COMPOSE) build

# ─── Smart rebuild targets ────────────────────────────────────────────────────
# These targets rebuild only what changed, then restart just that service.
# ML model volumes are NEVER touched — models stay cached between rebuilds.

## Smart rebuild: detect what changed and rebuild only that service
rebuild: check-env
	@echo "🔍  Checking what changed..."
	@if git diff --name-only 2>/dev/null | grep -q "^backend/"; then \
		echo "🔧  Backend changes detected — rebuilding backend only"; \
		$(MAKE) rebuild-backend; \
	elif git diff --name-only 2>/dev/null | grep -q "^frontend/"; then \
		echo "🔧  Frontend changes detected — rebuilding frontend only"; \
		$(MAKE) rebuild-frontend; \
	else \
		echo "🔧  Rebuilding all services (no git diff available)"; \
		$(COMPOSE) up --build -d; \
	fi

## Rebuild only the backend (no frontend rebuild, no model re-download)
rebuild-backend: check-env
	@echo "🔧  Building backend image (dep layers are cached)..."
	$(COMPOSE) build backend
	@echo "🔄  Restarting backend service..."
	$(COMPOSE) up -d --no-deps backend
	@echo "✅  Backend rebuilt and restarted."
	@echo "    Cache status:"
	@$(MAKE) cache-status --no-print-directory

## Rebuild only the frontend (no backend rebuild, no model re-download)
rebuild-frontend: check-env
	@echo "🔧  Building frontend image (npm cache reused)..."
	$(COMPOSE) build frontend
	@echo "🔄  Restarting frontend service..."
	$(COMPOSE) up -d --no-deps frontend
	@echo "✅  Frontend rebuilt and restarted."

# ─── ML model cache targets ───────────────────────────────────────────────────

## Show ML model cache status without starting any services
cache-status:
	@echo ""
	@echo "━━━  ML Model Volume Status ($(PROJECT_NAME))  ━━━"
	@echo ""
	@for vol in hf_cache torch_cache easyocr_cache yolo_cache deepface_cache numba_cache calibration_models; do \
		full_name="$(PROJECT_NAME)_$${vol}"; \
		if docker volume inspect $$full_name > /dev/null 2>&1; then \
			size=$$(docker run --rm -v $$full_name:/data alpine sh -c \
				"du -sh /data 2>/dev/null | cut -f1" 2>/dev/null || echo "?"); \
			echo "  ✅  $$vol  ($$size)"; \
		else \
			echo "  ⚠   $$vol  → NOT CREATED YET (will populate on first run)"; \
		fi; \
	done
	@echo ""

## Pre-warm model cache by running the cache check script inside a temp container
cache-warm: check-env
	@echo "🔥  Running model cache check inside backend container..."
	$(COMPOSE) run --rm --no-deps -e SKIP_CACHE_CHECK=0 backend \
		python scripts/model_cache_check.py
	@echo ""

# ─── Lifecycle targets ────────────────────────────────────────────────────────

## Stop all services — volumes are PRESERVED (models stay cached ✅)
down:
	$(COMPOSE) down
	@echo "✅  Services stopped. Model caches preserved."

## ⚠️  Stop AND delete ALL volumes (postgres data + ML models will be wiped!)
## Models take 15–60 min to re-download. Only use if you need a true clean slate.
down-clean:
	@echo ""
	@echo "⚠️  WARNING: This will DELETE all Docker volumes including:"
	@echo "    • All ML model caches (hf_cache, torch_cache, easyocr_cache, etc.)"
	@echo "    • PostgreSQL database data"
	@echo "    • Redis data"
	@echo ""
	@echo "    Models will be re-downloaded on next start (15–60 min)."
	@echo ""
	@read -p "    Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ] || (echo "Aborted." && exit 1)
	$(COMPOSE) down -v
	@echo "✅  All services and volumes removed."

## Follow logs for all services
logs:
	$(COMPOSE) logs -f

## Follow logs for a specific service: make logs-backend, make logs-frontend
logs-%:
	$(COMPOSE) logs -f $*

## Show running containers and health status
ps:
	$(COMPOSE) ps

## Production deploy (Caddy TLS, restart policies)
prod: check-env
	$(COMPOSE_PROD) up --build -d

## Remove dangling images to free disk space (safe — doesn't touch volumes)
prune:
	docker image prune -f
	@echo "✅  Dangling images removed."

## Full system prune: removes stopped containers, networks, dangling images
## Does NOT touch volumes.
prune-all:
	docker system prune -f
	@echo "✅  System pruned (volumes preserved)."

# ─── Environment check ────────────────────────────────────────────────────────

## Verify .env file exists and has required variables set
check-env:
	@if [ ! -f .env ]; then \
		echo ""; \
		echo "❌  ERROR: .env file not found."; \
		echo "    Run: cp .env.example .env"; \
		echo "    Then edit .env with your values."; \
		echo ""; \
		exit 1; \
	fi
	@if ! grep -q "NEXT_PUBLIC_DEMO_PASSWORD=" .env 2>/dev/null || \
	      grep -q "^NEXT_PUBLIC_DEMO_PASSWORD=$$" .env 2>/dev/null; then \
		echo ""; \
		echo "⚠️   WARNING: NEXT_PUBLIC_DEMO_PASSWORD is not set in .env"; \
		echo "    Edit .env and set a value for NEXT_PUBLIC_DEMO_PASSWORD."; \
		echo ""; \
	fi
