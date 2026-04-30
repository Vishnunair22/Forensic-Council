# Codebase Cleanup Trace

This repo is now a fresh-history working tree with generated dependencies and local outputs removed.

## Removed source files

- `apps/api/tools/model_cache.py` - unused cache wrapper; no imports referenced it.
- `apps/api/core/model_registry.py` - unused model registry prototype; no runtime or test imports referenced it.
- `apps/web/src/components/evidence/AnalysisProgressOverlay.tsx` - unused thin wrapper around `ForensicProgressOverlay`.
- `apps/web/src/components/evidence/ForensicTimeline.tsx` - unused timeline component.
- `apps/web/src/lib/logger.ts` - unused frontend logger utility.
- `apps/web/src/types/jest-axe.d.ts` - duplicate declaration already covered by `src/types/global.d.ts`.

## Removed local/generated directories

- `apps/api/.venv`
- `apps/api/.pytest_cache`
- `apps/api/cache`
- `apps/api/reports`
- `apps/web/node_modules`
- `apps/web/coverage`
- all Python `__pycache__` directories
- stale runtime uploads under `apps/api/storage/evidence/incoming`
- redundant placeholder files in non-empty or ignored directories

## Repaired source fixtures

- Renamed five JPEG-encoded test fixtures from `.png` to `.jpg` so file extensions match content signatures.

## Files to split or merge next

- `apps/api/core/react_loop.py` - very large orchestration engine. Split into planner, step execution, task override loading, and result serialization modules.
- `apps/api/core/gemini_client.py` - combines client setup, request shaping, retries, and response parsing. Split transport from prompt/response adapters.
- `apps/api/tools/audio_tools.py`, `apps/api/tools/image_tools.py`, `apps/api/tools/video_tools.py`, `apps/api/tools/metadata_tools.py` - keep separate by modality, but extract common result/error helpers and media probing helpers.
- `apps/api/core/handlers/image.py`, `scene.py`, `video.py`, `audio.py`, `metadata.py` - share a lot of handler flow. Move common tool execution and evidence-artifact assembly into `handlers/base.py`.
- `apps/api/api/main.py` - mixes app factory, middleware, health checks, lifecycle, and routes. Split middleware and health endpoints out of the app bootstrap file.
- `apps/api/api/routes/sessions.py` - route file also owns report-cache hydration and response shaping. Move cache/report lookup into a service module.
- `apps/api/core/rate_limit.py` and `apps/api/api/routes/_rate_limiting.py` - overlapping investigation rate-limit APIs. Keep one enforcement implementation and expose a compatibility wrapper only if tests or external callers still need it.
- `apps/api/core/rate_limiting.py` - generic fixed-window utility. Either make route rate limiting use it or rename it to clarify that it is test/infrastructure-only.
- `apps/web/src/hooks/useInvestigation.ts` and `apps/web/src/hooks/useSimulation.ts` - both are large state machines. Split API side effects, reducer/state transitions, and UI-facing selectors.
- `apps/web/src/components/ui/AgentFindingCard.tsx` and `apps/web/src/components/result/AgentFindingSubComponents.tsx` - presentation is split across `ui` and `result`; move the card fully under `components/result` or make it a generic UI component with no result-specific imports.

## Verification performed

- Python source AST parse passed across `apps/api`.
- Reference scan found no remaining imports/usages of the removed files.
- Generated dependency/cache directories are absent after cleanup.
- JSON/TOML parse checks passed.
- Image fixture signatures match file extensions after the fixture rename.
- Rough backend/frontend dead-source scans found no obvious unreferenced source files.
- Current counts after cleanup: 404 files on disk excluding `.git`, 403 source-control candidates excluding ignored local `.env`.
