# Docker Build Guide — Forensic Council

> **Version:** v1.5.0 | **Last Updated:** 2026-04-16

Complete reference for building, running, and managing the Forensic Council Docker stack from scratch.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Step 1 — Create `.env` File](#step-1--create-env-file)
3. [Step 2 — API Key Setup (Required)](#step-2--api-key-setup-required)
4. [Step 3 — Gemini Vision API Key (Recommended)](#step-3--gemini-vision-api-key-recommended)
5. [Step 4 — Build and Start](#step-5--build-and-start)
   - [Development Mode](#development-mode)
   - [Production Mode](#production-mode)
7. [First Run — ML Model Downloads](#first-run--ml-model-downloads)
8. [Model Caching — How It Works](#model-caching--how-it-works)
9. [Rebuilding With Model Cache](#rebuilding-with-model-cache)
10. [Management Commands](#management-commands)
11. [Troubleshooting Build Issues](#troubleshooting-build-issues)
12. [Troubleshooting Model Cache Issues](#troubleshooting-model-cache-issues)

---

## Prerequisites

- **Docker Desktop 23+** on Windows/macOS, or **Docker Engine 23+ + Compose v2** on Linux
- BuildKit must be enabled (default in Docker 23+; set `DOCKER_BUILDKIT=1` for older versions)
- Internet access for initial image build and ML model downloads
- Minimum 10–15 GB free disk space for ML model caches

Verify your setup:
```bash
docker --version       # Should be 23+
docker compose version # Should be v2.x
```

---

## Step 1 — Create `.env` File

The entire stack is configured via a single `.env` file at the project root.

```bash
# Linux / macOS
cp .env.example .env

# Windows PowerShell
Copy-Item .env.example .env
```

Open `.env` in your editor. The file has detailed comments for every variable. **Required changes before first run:**

```dotenv
# ─── REQUIRED: LLM API key (Step 2) ─────────────────────────────────────
LLM_API_KEY=gsk_your_key_here

# ─── RECOMMENDED: Gemini vision API key (Step 3) ────────────────────────
GEMINI_API_KEY=AIza_your_key_here

# ─── RECOMMENDED: Change demo passwords for any shared environment ───────
BOOTSTRAP_INVESTIGATOR_PASSWORD=inv123!
BOOTSTRAP_ADMIN_PASSWORD=admin123!
DEMO_PASSWORD=inv123!

# ─── RECOMMENDED: Generate a unique signing key ──────────────────────────
# Run: python -c "import secrets; print(secrets.token_hex(32))"
SIGNING_KEY=your-generated-64-char-hex-key
```

Everything else can be left at the defaults for local development.

---

## Step 2 — API Key Setup (Required)

The backend uses Groq (Llama 3.3 70B) to drive each agent's ReAct reasoning loop
and the Arbiter's executive summary synthesis. You need a Groq API key.

### Groq (Recommended — Free)

1. Go to [console.groq.com/keys](https://console.groq.com/keys)
2. Create a free account and generate an API key
3. In `.env`:
   ```dotenv
   LLM_PROVIDER=groq
   LLM_API_KEY=gsk_your_groq_key_here
   LLM_MODEL=llama-3.3-70b-versatile
   ```

- **Verification Scripts:** `validate_production_readiness.sh`.
- **Primary Vision Model:** `gemini-2.5-flash`
- **Orchestration Model:** `llama-3.3-70b-versatile`
- **Package Manager:** `uv 0.6.5`
 model provides strong reasoning for forensic analysis at ~700 tokens/second.

### OpenAI (Alternative)

```dotenv
LLM_PROVIDER=openai
LLM_API_KEY=sk-your-openai-key
LLM_MODEL=gpt-4o
```

### Run Without LLM (Tool-Only Mode)

To test the infrastructure without making LLM API calls:
```dotenv
LLM_PROVIDER=none
```

In this mode, agents run their ML tools but skip the LLM reasoning step. Gemini vision analysis still runs independently if `GEMINI_API_KEY` is set.

---

## Step 3 — Gemini Vision API Key (Recommended)

Agents 1 (Image Integrity), 3 (Object/Weapon), and 5 (Metadata/Context) use Google
Gemini during their **deep analysis pass** to:

- Identify what a file visually IS (photograph, screenshot, AI-generated image, document scan)
- Surface manipulation signals invisible to classical tools (visible editing boundaries, compositing artifacts)
- Validate whether visual content matches EXIF metadata claims (timestamp, GPS, capture device)
- Detect weapons, contraband, and contextual anomalies via vision

**Without the key:** Agents 1, 3, and 5 still run all their classical tools (ELA, YOLO,
EXIF extraction, etc.). Gemini analysis tasks are skipped with a warning recorded in the
finding's `caveat` field.

**To enable Gemini vision:**

1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Sign in with a Google account and generate a free API key
3. In `.env`:
   ```dotenv
   GEMINI_MODEL=gemini-2.5-flash                            # Primary model (stable free-tier)
   GEMINI_FALLBACK_MODELS=gemini-2.0-flash,gemini-2.0-flash-lite  # Ordered fallback chain
   GEMINI_TIMEOUT=55.0                                            # API timeout in seconds
   ```

   The client automatically cascades through the fallback chain if the primary model is unavailable (404) or rate-limited after retries. Each fallback is tried in order; the first successful response wins.

> **Free tier:** Google AI Studio's free tier supports the Gemini 2.5 and 2.0 series. `gemini-2.5-flash` is verified as the most stable primary for v1.3.0.

---

## Step 4 — Build and Start

### Development Mode

Development mode mounts source code as volumes and enables hot-reload for both services. Use this for active development.

**Linux / macOS / Windows (run from the project root):**
```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.dev.yml \
  --env-file .env \
  up --build
```

What you get:
- **Backend:** Uvicorn with `--reload` watching all `.py` files — save a file, the API restarts in ~1 s
- **Frontend:** Next.js dev server with Fast Refresh — React changes reflect instantly without a full reload
- **Named volumes** for all ML model caches (`hf_cache`, `yolo_cache`, etc.) — shared with production so models never re-download when you switch modes
- **`nextjs_cache` volume** preserves the Next.js webpack compilation cache across container restarts — avoids the ~120 s cold-compile on every `docker compose up`
- `/api/v1/` Swagger docs at http://localhost:8000/docs

> **Note:** The dev override (`docker-compose.dev.yml`) raises the frontend memory limit to 2 GB / 2 CPUs. Next.js dev-mode webpack compilation is memory-heavy (~900 MB peak). Running with the production limit (512 MB) causes OOM kills and container restart loops.

### Production Mode

Production mode uses multi-stage Docker builds with optimized images.

**Linux / macOS / Windows:**
```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.prod.yml \
  --env-file .env \
  up --build -d
```

What you get:
- Backend: Gunicorn/Uvicorn worker pool, `read_only` filesystem
- Frontend: Next.js standalone build served via node (behind Caddy)
- Caddy: Reverse proxy on ports 80/443 with automatic TLS

### Starting Infrastructure Only

If you want to run the backend natively (outside Docker) but need the databases:

```bash
docker compose \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.infra.yml \
  --env-file .env up -d
```

This starts only Postgres, Redis, and Qdrant.

---

## First Run — ML Model Downloads

On first start, each ML model downloads automatically from its provider. This is expected and only happens once.

**Expected download times (depends on connection speed):**

| Model | Provider | Size | Downloaded When |
|-------|----------|------|----------------|
| `llama-3.3-70b` via Groq API | Remote API | — | On first investigation |
| Wav2Vec2 | HuggingFace | ~1.2 GB | Agent 2 first run |
| CLIP ViT-L/14 | HuggingFace | ~890 MB | Agent 3 first run |
| YOLOv8n | Ultralytics | ~6 MB | Agent 3 first run |
| DeepFace models | GitHub releases | ~500 MB | Agent 3 first run |
| EasyOCR | EasyOCR CDN | ~120 MB | Agent 1 first run |

**Total: ~4–15 GB depending on which models are downloaded**

The startup log shows cache status before the API starts:

```
━━━  ML Model Cache Status  ━━━
  ⚠ EMPTY    HuggingFace          (will download on first use)
  ⚠ EMPTY    PyTorch              (will download on first use)
  ✓ CACHED   YOLO          6 MB   (4 files)
  ...
  3 of 7 cache directories are empty.
  Models download automatically on first investigation.
```

Once downloaded, models are stored in Docker named volumes and persist indefinitely.

---

## Model Caching — How It Works

ML model weights are stored in **Docker named volumes**, not inside the image. This means:

- They persist across `docker compose down` and back up
- They persist across full image rebuilds (`--no-cache`)
- They are **shared between dev and production** stacks (same project name = same volumes)
- They are **only deleted** by `docker compose down -v` or manually via `docker volume rm`

### Named volumes and their contents

| Volume Name | Contents | Approx Size |
|-------------|----------|-------------|
| `forensic-council_hf_cache` | HuggingFace models (Wav2Vec2, CLIP, pyannote) | 3–15 GB |
| `forensic-council_torch_cache` | PyTorch hub checkpoints | 500 MB – 2 GB |
| `forensic-council_easyocr_cache` | EasyOCR text recognition weights | ~120 MB |
| `forensic-council_yolo_cache` | YOLOv8 object detection weights | ~50 MB |
| `forensic-council_numba_cache` | Numba JIT compiled kernels | ~100 MB |
| `forensic-council_calibration_models_cache` | Platt scaling calibration checkpoints | ~10 MB |

### Check current volume sizes

```bash
docker system df -v | grep forensic
```

### Why dev and prod share volumes

Both `docker-compose.dev.yml` and `docker-compose.prod.yml` are layered on top of `docker-compose.yml`. The base file has `name: forensic-council`, and `.env` has `COMPOSE_PROJECT_NAME=forensic-council`. Docker uses this name to prefix all named volumes — ensuring both stacks share the same `forensic-council_hf_cache`, etc.

Without this, switching from dev to prod would trigger a full model re-download.

---

## Rebuilding With Model Cache

### Code changes only (fastest — ~30–90 seconds)

```bash
docker compose -f infra/docker-compose.yml --env-file .env up --build -d
```

Docker only rebuilds the final code layer. All dependency layers and ML model volumes are reused.

### Dependency changes (medium — ~2–8 minutes)

When `pyproject.toml` or `package.json` change:
```bash
# Docker rebuilds the deps layer, but uv/npm use BuildKit cache for unchanged packages
docker compose -f infra/docker-compose.yml --env-file .env up --build -d
```

### Rebuild one service only

```bash
# Rebuild and restart backend only (zero downtime for frontend)
docker compose -f infra/docker-compose.yml --env-file .env build backend
docker compose -f infra/docker-compose.yml --env-file .env up -d --no-deps backend
```

### Full no-cache rebuild (nuclear — preserves ML volumes)

```bash
docker compose -f infra/docker-compose.yml --env-file .env build --no-cache
docker compose -f infra/docker-compose.yml --env-file .env up -d
```

> `--no-cache` bypasses Docker layer cache only. Named volumes (ML models) are **not** affected.

### Delete a single model cache (targeted re-download)

```bash
# Delete only EasyOCR models
docker volume rm forensic-council_easyocr_cache

# Models re-download automatically on next container start
docker compose -f infra/docker-compose.yml --env-file .env up -d backend
```

### Full reset including all models (⚠️ long re-download)

```bash
docker compose -f infra/docker-compose.yml --env-file .env down -v
# All volumes deleted — models re-download on next start (15–60 min)
```

---

| Action | Command |
|--------|---------|
| Start production | `docker compose -f infra/docker-compose.yml --env-file .env up -d --build` |
| Start dev | `docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml --env-file .env up --build` |
| Start production-optimized | `docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml --env-file .env up -d --build` |
| Infrastructure only | `docker compose -f infra/docker-compose.yml -f infra/docker-compose.infra.yml --env-file .env up -d` |
| Stop (keep volumes) | `docker compose -f infra/docker-compose.yml --env-file .env down` |
| Stop (delete volumes) | `docker compose -f infra/docker-compose.yml --env-file .env down -v` |
| View logs | `docker compose -f infra/docker-compose.yml --env-file .env logs -f` |
| Check ML cache | `docker system df -v \| grep forensic` |

---

## Troubleshooting Build Issues

### `DOCKER_BUILDKIT` not enabled (Docker < 23)

```bash
DOCKER_BUILDKIT=1 docker compose -f infra/docker-compose.yml --env-file .env up --build
```

### `uv sync` fails during backend build

1. Check internet access to PyPI
2. Ensure `uv.lock` is not corrupted: `cd apps/api && uv lock`
3. Try BuildKit prune: `docker builder prune -f` then rebuild

### `npm ci` fails with `eslint-config-next` version error

Next.js 15 uses Webpack for production builds; ESLint runs during `next build`. Ensure `eslint` and `eslint-config-next` are on matching major versions (both `^9` / `^15` respectively).

### `DEMO_PASSWORD not set` error

The compose file uses `:?` guards. Ensure `.env` has this variable uncommented:
```bash
grep DEMO_PASSWORD .env
# Should show: DEMO_PASSWORD=inv123!
```

### Old code running after rebuild

The old container wasn't replaced. Force recreate:
```bash
docker compose -f infra/docker-compose.yml --env-file .env up --build -d --force-recreate
```

### Frontend shows old UI after changing `NEXT_PUBLIC_*` variables

These variables are baked into the JS bundle at build time. You must rebuild:
```bash
docker compose -f infra/docker-compose.yml --env-file .env build frontend
docker compose -f infra/docker-compose.yml --env-file .env up -d --no-deps frontend
```

### Backend `read_only: true` permission errors

The backend runs with a read-only filesystem for security. Writable paths must be tmpfs or named volumes. If you see permission errors for paths like `/tmp`, `/app/storage`, or `/app/cache`, check that the compose file has:
```yaml
read_only: true
tmpfs:
  - /tmp:nosuid,size=512m
volumes:
  - evidence_data:/app/storage/evidence:rw
  - hf_cache:/app/cache/huggingface:rw
```
`/tmp` is the only tmpfs mount. All other writable paths (`/app/storage/evidence`, `/app/cache`, and the individual model sub-caches) are backed by named volumes defined in the `volumes:` block.

---

## Troubleshooting Model Cache Issues

### Models re-downloading after every rebuild

**Cause:** `docker compose down -v` was run, deleting all volumes.

**Fix:** There is no fix — models must re-download. This takes 15–60 min once. Avoid `down -v` in future.

**Check:** `docker volume ls | grep forensic-council`
If volumes are missing, they will be created fresh on next start.

### One agent fails but others work

A specific model cache may be corrupted or empty.

```bash
# Check which volumes are populated
docker system df -v | grep forensic

# Delete just the affected cache
docker volume rm forensic-council_hf_cache   # if HuggingFace models are corrupt
docker compose -f infra/docker-compose.yml --env-file .env up -d backend
```

### HuggingFace download stuck at 0%

1. Verify internet access inside container: `docker exec forensic-council-backend-1 curl -I https://huggingface.co`
2. HuggingFace may be rate-limiting. Wait and retry.

### Model cache not shared between dev and prod

**Cause:** Project name mismatch. Docker is using different volume prefixes.

**Fix:**
```bash
# Verify both .env and docker-compose.yml have the same project name
grep COMPOSE_PROJECT_NAME .env           # Should be: forensic-council
grep "^name:" infra/docker-compose.yml  # Should be: forensic-council

# Check actual volume names
docker volume ls | grep forensic
# All should start with: forensic-council_
```

### Backend starts but model_cache_check shows all EMPTY

First run — this is normal. Models download on first investigation, not at startup. The check script is informational only and never blocks startup.

To skip the cache check (CI/CD):
```bash
# In .env or compose environment:
SKIP_CACHE_CHECK=1
```

### BuildKit cache taking too much disk space

```bash
# Check size
docker builder du

# Prune unused caches (safe — won't affect running containers or volumes)
docker builder prune -f

# Nuclear option — prune everything
docker builder prune --all -f
```

---

## Production HTTPS (Optional)

Caddy handles TLS automatically via Let's Encrypt when a public domain is configured.

1. Point your domain's DNS A record to your server's public IP
2. Ensure ports 80 and 443 are open in your firewall
3. In `.env`:
   ```dotenv
   DOMAIN=forensic.yourdomain.com
   ```
4. Restart Caddy:
   ```bash
   docker compose -f infra/docker-compose.yml --env-file .env up -d caddy
   ```

Caddy will automatically obtain and renew the Let's Encrypt certificate.

> ⚠️ Without a domain configured, Caddy serves on port 80 with a self-signed certificate. Never run with plain HTTP in production — JWT tokens and evidence files are transmitted in cleartext without TLS.


