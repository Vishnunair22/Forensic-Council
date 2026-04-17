# Technology Stack

**Analysis Date:** 2026-04-17 (Post-Audit Refresh)

## Languages

**Primary:**
- Python 3.12 - FastAPI backend, agents, tools, ML pipeline (`apps/api/`)
- TypeScript 5.8.3 - Next.js frontend (`apps/web/`)

**Secondary:**
- CSS / Vanilla CSS + Tailwind CSS 4.x - UI styling (`apps/web/src/app/globals.css`)

## Runtime

**Environment:**
- Python: `>=3.11,<3.15` (Docker image pins Python 3.12-slim-bookworm)
- Node.js: `>=22.0.0` (pinned via `apps/web/.node-version`)

**Package Manager:**
- Backend: `uv` 0.6.5 (pinned in `apps/api/Dockerfile`)
- Frontend: `npm` with lockfile at `apps/web/package-lock.json`
- Lockfiles: `apps/api/uv.lock` (present), `apps/web/package-lock.json` (present)

## Frameworks

**Core (Backend):**
- FastAPI `>=0.115.12` - REST API + WebSocket server (`apps/api/api/main.py`)
- Uvicorn `>=0.34` (standard) - ASGI server with WebSocket support
- Pydantic v2 `>=2.11` - data validation and settings (`apps/api/core/config.py`)
- Pydantic Settings `>=2.9` - environment-based config (`apps/api/core/config.py`)

**Core (Frontend):**
- Next.js `^15.5.14` (App Router, standalone output mode) - `apps/web/`
- React `^19.2.4` + React DOM - component framework
- TailwindCSS `^4.2.2` + `@tailwindcss/postcss` - utility CSS
- Framer Motion `^12.38.0` - animations and transitions
- Zod `^3.24.0` - runtime schema validation for API responses (`apps/web/src/lib/schemas.ts`)

**UI Components:**
- `@radix-ui/react-dialog ^1.1.15` - accessible dialog primitives
- `lucide-react ^1.6.0` - icon library
- `class-variance-authority ^0.7.1` + `clsx ^2.1.1` + `tailwind-merge ^3.5.0` - conditional class utilities

**Build/Dev (Backend):**
- Ruff `>=0.9` - linting (`apps/api/pyproject.toml`, line-length 100, py312 target)
- Pyright `1.1.400` - type checking (strict mode on `core/auth.py`, `core/signing.py`, `core/circuit_breaker.py`)
- Pytest `>=8.4` + `pytest-asyncio >=1.0` + `pytest-cov >=6.1` + `pytest-mock >=3.14`
- Faker `>=26.0` + Factory Boy `>=3.3` - test data factories

**Build/Dev (Frontend):**
- ESLint `^9.39.4` + `eslint-config-next ^15.5.14` + `eslint-plugin-jsx-a11y` - linting
- Jest `^30.3.0` + `jest-environment-jsdom` + `ts-jest ^29.4.6` - unit testing
- `@testing-library/react ^16.3.0` + `@testing-library/user-event` - component testing
- Playwright `^1.59.1` - E2E testing (installed but CI not wired)
- `@axe-core/react ^4.10.1` + `jest-axe ^10.0.0` - accessibility testing
- Turbopack (Next.js 15 default bundler; webpack retained for Docker bind mounts)

## Key Dependencies

**AI / ML (Backend core extras - `pyproject.toml [ml]`):**
- `groq >=0.28` - Groq API client for Llama 3.3 70B inference (`apps/api/core/llm_client.py`)
- `google-generativeai >=0.8` - Google Gemini 2.0 Flash/Pro vision API (`apps/api/core/gemini_client.py`)
- `torch >=2.7` (CPU-only via pytorch-cpu index) + `torchvision >=0.22` + `torchaudio >=2.7`
- `ultralytics >=8.3` - YOLOv8/YOLO11 object detection (model: `yolo11m.pt`)
- `open-clip-torch >=2.30` - CLIP image embedding
- `transformers >=4.52` + `accelerate >=1.7` - HuggingFace transformers
- `speechbrain >=1.0` - AASIST anti-spoofing (voice clone detection)

**Image Processing:**
- `Pillow >=11.2`, `numpy >=1.26,<3.0`, `scipy >=1.15`, `scikit-image >=0.25`
- `opencv-contrib-python >=4.9` - SIFT copy-move detection
- `piexif >=1.1`, `imagehash >=4.3`, `stegano >=0.11` (LSB steganography)
- `hachoir >=3.2` - binary container metadata parsing

**Audio Processing:**
- `librosa >=0.10`, `soundfile >=0.12`
- `praat-parselmouth >=0.4` - F0/jitter/shimmer prosody analysis
- `moviepy >=1.0,<2.0` - AV sync via video+audio correlation

**OCR:**
- `PyMuPDF >=1.25` - PDF lossless text/image/metadata extraction
- `easyocr >=1.7.2` - neural OCR (80+ languages)
- `pytesseract >=0.3.13` - Tesseract OCR wrapper

**Metadata:**
- `pyexiftool >=0.5`, `piexif >=1.1` - EXIF metadata
- `geopy >=2.4`, `timezonefinder >=6.2`, `astral >=3.2` - geospatial/astronomical validation
- `pymediainfo >=6.1.0` - AV container deep analysis

**Infrastructure (Backend):**
- `asyncpg >=0.30` - async PostgreSQL driver (`apps/api/core/persistence/postgres_client.py`)
- `redis >=5.3` (redis.asyncio) - async Redis client (`apps/api/core/persistence/redis_client.py`)
- `qdrant-client ==1.16.2` - async Qdrant vector DB client (`apps/api/core/persistence/qdrant_client.py`)
- `httpx >=0.28` - async HTTP client (used by LLM/Gemini clients)
- `websockets >=15.0` - WebSocket support

**Auth (Backend):**
- `python-jose[cryptography] >=3.5` - JWT encode/decode (`apps/api/core/auth.py`)
- `passlib[bcrypt] >=1.7.4` + `bcrypt >=4.0.1,<5.0` - password hashing (12 rounds)
- `cryptography >=44` - ECDSA P-256 chain-of-custody signing (`apps/api/core/signing.py`)

**Security (optional extra):**
- `fastapi-csrf-protect >=0.3.3`

**Observability (optional extra):**
- `opentelemetry-api >=1.20` + `opentelemetry-sdk >=1.20`
- `opentelemetry-exporter-otlp-proto-grpc >=1.20` - OTLP gRPC exporter (targets Jaeger)
- `opentelemetry-instrumentation-fastapi >=0.41b0`
- `opentelemetry-instrumentation-redis >=0.41b0`
- `opentelemetry-instrumentation-sqlalchemy >=0.41b0`

## Configuration

**Environment:**
- All config centralized in `apps/api/core/config.py` via `pydantic_settings.BaseSettings`
- Config loaded from `.env` or `../.env` relative to app root
- Environment variables override file values; unknown vars are ignored
- Template: `.env.example` at monorepo root
- Key required vars: `SIGNING_KEY`, `JWT_SECRET_KEY`, `LLM_API_KEY`, `GEMINI_API_KEY`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`
- Production mode enforces entropy/length validation and blocks insecure defaults at startup via `validate_production_settings()`
- Frontend env vars prefixed `NEXT_PUBLIC_*` are baked into JS bundle at build time; `DEMO_PASSWORD` is server-side only

**Build (Backend):**
- `apps/api/pyproject.toml` - project metadata, deps, tool config (ruff, pyright, pytest, coverage)
- `apps/api/Dockerfile` - multi-stage build: `base` → `deps-core` / `deps-full` → `migration` / `app` → `development` / `production`
- ML model caches mapped to named Docker volumes: `hf_cache`, `torch_cache`, `easyocr_cache`, `numba_cache`, `yolo_cache`
- System deps installed in Docker: `tesseract-ocr`, `exiftool`, `ffmpeg`, `libmagic-dev`, `libmediainfo-dev`, `libgl1`

**Build (Frontend):**
- `apps/web/package.json` - v1.4.0, Node >=22
- `apps/web/next.config.ts` - standalone output, Turbopack resolver config, compression disabled (Caddy handles it)
- `apps/web/tsconfig.json` - TypeScript config

## Platform Requirements

**Development:**
- Docker + Docker Compose (Docker 23+ for BuildKit default)
- OR: Python 3.12 + uv (backend), Node 22 + npm (frontend)
- System binaries: `tesseract`, `exiftool`, `ffmpeg` (validated at startup)

**Production:**
- Docker Compose with 5 core services + 1 migration runner
- Memory: backend container limited to 4 GB, Qdrant 1 GB, Postgres 1 GB, Redis 512 MB, frontend 512 MB
- Reverse proxy: Caddy 2 (TLS termination, Let's Encrypt ACME, security headers, 55 MB upload limit)
- Network segmentation: `infra_net` (backend ↔ datastores), `backend_net` (frontend ↔ backend), `frontend_net` (Caddy ↔ frontend)
- Read-only filesystem for backend and worker containers; writable tmpfs at `/tmp`

---

*Stack analysis: 2026-04-17*
