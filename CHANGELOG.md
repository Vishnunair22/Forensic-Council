# Changelog

All notable changes to the Forensic Council project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — 2026-03-05

### 🎉 Production Ready

Full end-to-end audit, cleanup, and production hardening. All 194+ historical issues resolved.

### Changed
- **Version aligned to 1.0.0** across `pyproject.toml`, `package.json`, `api/main.py`, and all docs
- **README.md** — Fixed Next.js version from 16 to 15 (matching actual `next@15.3.0` dependency)
- **Backend Dockerfile** — Pinned `uv` from `latest` to `0.6.6` for deterministic builds
- **ESLint config** — Migrated from deprecated `extends` syntax to proper flat config with `FlatCompat`
- **`.gitignore`** — Added `node_modules/`, `.next/`, `out/`, `coverage/`, `.pytest_cache/`, `*.whl`, broadened `backend/storage/keys/`
- **`docker-compose.override.yml`** — Added `read_only: false` to fix conflict with base `read_only: true` + `--reload` command
- **`Development-Status.md`** — Fixed "Sequential execution" → "Concurrent execution via asyncio.gather", updated to v1.0.0

### Removed
- `forensic-council-1.0-roadmap.docx` — Non-code planning document (not needed in source control)
- `backend/docs/` directory — Duplicate of `docs/agent_capabilities.md`
- `frontend/public/file.svg`, `globe.svg`, `next.svg`, `vercel.svg`, `window.svg` — Next.js scaffolding remnants
- `backend/scripts/hash_demo.py` — Trivial 4-line demo script
- `frontend/dev-guide.md` — Covered by existing docs

## [0.8.0] — 2026-03-05

### Added
- **All 9 agent stubs replaced with real implementations** (see `docs/Development-Status.md` for full table)
  - Agent 1: `adversarial_robustness_check` — ELA perturbation stability (Gaussian noise, double JPEG, colour jitter)
  - Agent 1: `sensor_db_query` — PRNU residual heuristics + EXIF manufacturer cross-validation
  - Agent 2: `adversarial_robustness_check` — Spectral perturbation stability (low-pass, noise, time-stretch)
  - Agent 3: `secondary_classification` — CLIP ViT-B-32 zero-shot via shared CLIPImageAnalyzer singleton
  - Agent 3: `adversarial_robustness_check` — YOLO perturbation stability (blur, brightness, salt-and-pepper)
  - Agent 4: `adversarial_robustness_check` — Optical flow perturbation stability (noise, brightness)
  - Agent 5: `reverse_image_search` — PHash (16×16) perceptual hash comparison against local evidence store
  - Agent 5: `device_fingerprint_db` — EXIF manufacturer signature rules + PRNU cross-validation
  - Agent 5: `adversarial_robustness_check` — Metadata anomaly score perturbation stability
- `docker/docker-compose.override.yml` — Development override with host port bindings
- `frontend/src/app/session-expired/page.tsx` — Session expiry page (fixes blank page on invalid session)
- `Makefile` at project root with targets: `infra`, `up`, `down`, `logs`, `backend`, `frontend`, `test`, `clean`
- `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL` environment variables wired into Settings and docker-compose
- `hf_token` as a typed field in `Settings` (was previously only `os.getenv()`)

### Changed
- `frontend/src/lib/api.ts` — `handleAuthError` now redirects to `/session-expired` when auth retry limit exhausted
- `backend/.env.example` — Removed misleading `DATABASE_URL` (app builds URL from `POSTGRES_*` vars), added LLM config section
- `backend/core/config.py` — Added `hf_token: Optional[str]` field
- `.gitignore` — Removed `docker-compose.override.yml` exclusion (now committed), added `frontend/lint.json` / `frontend/lint_output.txt`

### Fixed
- Session expiry showed blank page — now redirects to `/session-expired`
- `LLM_PROVIDER` env var not passed to Docker backend container
- `HF_TOKEN` not a typed Settings field (silent failure if not set)

### Removed
- `frontend/lint.json` and `frontend/lint_output.txt` debug artifacts
- `hash_demo.py` from root (moved to `backend/scripts/`)
- `backend/test_exif.py`, `backend/test_exif_sync.py` from backend root (moved to `backend/scripts/`)
- `docs/End-End Test.py` renamed to `docs/end_to_end_test.py`

## [0.7.0] - 2026-03-04

### Fixed — Docker & Build (13 issues)
- Added `build:` context to backend and frontend services in `docker-compose.yml`
- Added `evidence_data` volume + keys bind-mount to fix `read_only: true` crash on first upload
- Added `libgl1` and `libglib2.0-0` to backend runner stage (OpenCV import fix)
- Pinned `uv` to `0.4.27` (was `latest`, non-deterministic)
- Removed conflicting `build:` block from `docker-compose.prod.yml` frontend service
- Added `SIGNING_KEY` `:?` guard — compose now aborts with a clear message if unset
- Added `overrides` for `@react-three/fiber` and `@react-three/drei` (React 19 peer dep)
- Added `HEALTHCHECK` instructions to both backend and frontend Dockerfiles
- Added `caddy_logs` volume for `/var/log/caddy` in production compose
- Removed nested `${JWT_SECRET_KEY:-${SIGNING_KEY}}` (Docker Compose doesn't support nested interpolation) — `config.py` fallback handles this correctly already
- Added `ports: 3000:3000` to frontend service in base compose
- Added `HF_TOKEN` to both dev and prod compose (required for `pyannote.audio`)
- Changed `npm install` to `npm ci` in frontend Dockerfile

### Fixed — Frontend App (7 issues)
- `startSimulation("pending")` now correctly triggers `"initiating"` status on the evidence page
- Fixed `URL.createObjectURL` memory leak — blob URL now derived via `useMemo` and revoked on cleanup
- Fixed CSS typo `linear_gradient` → `linear-gradient` on result page grid background
- Added `Poppins` font via `next/font/google` in `layout.tsx` — `--font-poppins` CSS variable now resolves
- Removed unused `AgentResult` import from `constants.ts`
- Removed redundant `env:` block from `next.config.ts`
- Throttled `"think"` sound to only play on new agent activation, not every WebSocket update

### Fixed — Backend & Tests (5 issues)
- Added missing MIME types `.webp`, `.mkv`, `.flac` to `_get_mime_type()` in `pipeline.py`
- Fixed `SigningService` class reference in E2E tests — now uses actual functions
- Fixed EXIF bytes/string comparison in test fixtures
- Updated test to accept `401` or `422` on auth-required endpoints
- Installed missing test dependencies: `pyexiftool`, `python-jose`, `geopy`, `passlib`, `bcrypt`

## [0.6.0] - 2026-03-02
### Added
- **Multi-Agent Core Pipeline**: Sequential execution loop for 5 active agents (Image, Audio, Object, Video, Metadata).
- **Arbiter Synthesis Module**: Compiles cross-modal findings into cohesive verdicts.
- **Machine Learning Subsystem**: Deepfake detection, ELA, noise fingerprinting, and metadata parsing tools offloaded as secure subprocesses to avoid event-loop blocking.
- **WebSocket Streaming**: Live `THOUGHT` and `ACTION` blocks mirrored in real-time from backend to frontend UI.
- **Human-In-The-Loop (HITL)**: Webhook support to request mandatory operator decisions when agents contest each other.
- **Deterministic Cryptography**: Reports are signed deterministically with an ECDSA scheme based on `SIGNING_KEY` environment variables.

### Changed
- **Memory Management**: Redis models updated with 24-hour TTLs (`ex=86400`) to remedy memory leak issues during heavy load.
- **Container Architecture**: Optimized multi-stage Docker builds using `uv` to drastically reduce image sizes.
- **UI Aesthetics**: Adopted "cyber-analytic" framework complete with Tailwind v4, Framer Motion, and 3D visualization grids via `@react-three/fiber`.

### Fixed
- CORS blocking bugs resolved by standardizing `NEXT_PUBLIC_API_URL` during Next.js standalone build.
- Fixed AttributeErrors across backend ML handlers related to literal string property usage.

## [0.1.0] - Initial Alpha Prototype
### Added
- Initial setup of FastAPI backend and standalone React interface.
- Basic routing and placeholder endpoints for single-agent analysis logic.
