# Local Development Setup

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.12 | `pyenv install 3.12` |
| Node.js | 22 | `nvm install 22` |
| Docker | 23+ | [docker.com](https://docs.docker.com/get-docker/) |
| Git | 2.40+ | [git-scm.com](https://git-scm.com/) |
| FFmpeg | 6.0+ | `brew install ffmpeg` / `choco install ffmpeg` |
| ExifTool | 12.60+ | `brew install exiftool` / `choco install exiftool` |
| Tesseract | 5.3+ | `brew install tesseract` / `choco install tesseract` |

Version files `.python-version`, `.node-version`, and `.nvmrc` are included so pyenv/nvm/fnm auto-detect the correct versions.

---

## Backend Setup

```bash
cd apps/api

# Install uv (fast Python package manager)
pip install uv

# Install all dependencies (including ML runtimes)
uv sync --all-extras

# Copy environment variables
cp .env.example .env

# Start infrastructure only (Postgres, Redis, Qdrant)
docker compose -f ../infra/docker-compose.yml -f ../infra/docker-compose.infra.yml up -d

# Run migrations
uv run alembic upgrade head

# Start dev server with hot-reload
uv run uvicorn api.main:app --reload --port 8000
```

API is now at `http://localhost:8000`. Swagger docs at `http://localhost:8000/docs`.

---

## Frontend Setup

```bash
cd apps/web

# Install dependencies
npm install

# Start dev server
npm run dev
```

Frontend is now at `http://localhost:3000`.

---

## Full Docker Stack

To run everything in Docker (backend + frontend + infrastructure):

```bash
cp .env.example .env
# Edit .env with your API keys

docker compose -f infra/docker-compose.yml --env-file .env up --build
```

---

## Running Tests

```bash
# Backend
cd apps/api && uv run pytest tests/ -v

# Frontend
cd apps/web && npm test -- --watchAll=false

# Lint
cd apps/api && uv run ruff check .
cd apps/web && npm run lint
```

---

## Common Issues

### `ModuleNotFoundError` on backend start
Run `uv sync --all-extras` from the `apps/api/` directory. The virtualenv is managed by uv.

### Frontend `EACCES` permission error
Delete `node_modules` and reinstall: `rm -rf node_modules && npm install`

### Docker port conflict (5432/6379)
Another Postgres or Redis instance is running. Stop it or change ports in `.env`.

### `GEMINI_API_KEY not set` warning
This is normal for local development. Agents 1, 3, 5 will use local fallback analysis. Set the key in `.env` to enable Gemini vision.

#### Recommended Models (v1.4.0 Standard)
For optimal forensic precision, use the following in your `.env`:
- `LLM_MODEL=llama-3.3-70b-versatile` (Groq)
- `GEMINI_MODEL=gemini-2.5-flash` (Google AI Studio)
