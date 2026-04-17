# Requirements — Final Codebase Audit & Refinement
**Version:** 1.0 (Audit Cycle)
**Created:** 2026-04-16

---

## Phase 1: Structural Check
- [ ] **STR-01**: Inventory all files and identify stray, duplicate, or unwanted artifacts (e.g. `.pyc`, `__pycache__`, legacy temp files).
- [ ] **STR-02**: Verify all files are in their proper semantic folders (monorepo compliance).
- [ ] **STR-03**: Validate all internal import paths and relative references across `apps/api` and `apps/web`.
- [ ] **STR-04**: Identification of "dead" paths or broken links in documentation and config files.

## Phase 2: Logic Consolidation (Completed)
- [x] **LOG-01**: Extract `_TOOL_RELIABILITY_TIERS` and verdict thresholds into `core/forensic_policy.py`.
- [x] **LOG-02**: Migrate social media compression detection from Arbiter to `MetadataAgent`.
- [x] **LOG-03**: Relocate `apps/api/scratch` to `.planning/scratch` and clean root `pytest.ini`.

## Phase 3: API Client & Polish (Completed)
- [x] **POL-01**: Implement "Partial Validation" for reports in `api.ts` to prevent breakage on schema updates.
- [x] **POL-02**: Standardize WebSocket base URL using relative paths/env vars.
- [x] **POL-03**: Refactor `api.ts` into separated modules (Types, Client, Utils).

## Phase 4: Base Class Decomposition (Completed)
- [x] **REF-01**: Decompose `ForensicAgent` into specialized mixins (Memory, Context, Investigation, Reflection).
- [x] **REF-02**: Implement modular mixin-based architecture across all agents.

## Phase 5: Docker Build Prep
- [x] **DOCK-01**: Purge all local transient caches (`.pytest_cache`, `__pycache__`, `/app/cache/*`).
- [x] **DOCK-02**: Inject provided Groq API key (`llama-3.3-70b-versatile`) and Gemini API key (`gemini-2.5-flash`) into `.env` files.
- [x] **DOCK-03**: Configure robust Gemini fallback chain (`gemini-2.5-flash` -> `gemini-2.0-flash` -> `gemini-2.0-flash-lite`).
- [x] **DOCK-04**: Final sanity check of `Dockerfile` layers and `docker_entrypoint.sh` for production readiness.

### Phase 6: Docker Dev Build
- [ ] **DEV-01**: Deep clean of Docker engine (prune images, containers, networks, and build cache).
- [ ] **DEV-02**: Reset environment to `development` mode (`APP_ENV=development`, `DEBUG=true`) while preserving production-grade keys.
- [ ] **DEV-03**: Execute `docker compose -f docker-compose.dev.yml up --build` with verified volume mounts.
- [ ] **DEV-04**: Verify health status of all 5+ core services (FastAPI, Redis, Postgres, Qdrant, Next.js).
