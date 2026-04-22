# AGENTS.md — AI Assistant Context for Forensic Council

Welcome, AI Assistant. This file provides essential context for working on the Forensic Council monorepo.

## Project Overview

**Forensic Council** is a multi-agent forensic tribunal system for digital media verification. Upload evidence, five specialized AI agents analyze it, and receive a cryptographically signed forensic report.

### Tech Stack

- **Frontend**: Next.js 15 (App Router), TypeScript, TailwindCSS, Framer Motion
- **Backend**: FastAPI (Python 3.12), asyncio, ReAct Agent Loops
- **AI/ML**: Groq (Llama 3.3 70B), Google Gemini 2.0 Flash (Vision), YOLO11 (Object Detection)
- **Infrastructure**: Redis (Working Memory), PostgreSQL 17 (Custody Ledger), Qdrant (Episodic Memory), Docker, Caddy 2

### Monorepo Structure

```
.
├── apps/
│   ├── api/          # Python FastAPI backend
│   │   ├── agents/   # 5 forensic agents + Arbiter
│   │   ├── core/     # Shared infrastructure (persistence, orchestration)
│   │   ├── api/      # FastAPI routes/schemas
│   │   └── tools/    # Domain-specific analysis tools
│   └── web/          # Next.js 15 frontend
│       ├── src/
│       │   ├── app/          # App Router pages
│       │   ├── components/   # React components
│       │   ├── hooks/        # Custom React hooks
│       │   └── lib/          # Utilities, API client, storage
│       └── public/
├── infra/            # Docker Compose, Caddy config, scripts
├── docs/             # Architecture, API, state docs
└── .env.example      # Environment template
```

## Key Commands

### Backend (Python)

```bash
# Install dependencies
cd apps/api && uv sync

# Run development server
uv run uvicorn api.main:app --reload --port 8000

# Run tests
uv run pytest tests/ -v

# Lint
uv run ruff check .

# Type check
uv run pyright .
```

### Frontend (TypeScript)

```bash
# Install dependencies
cd apps/web && npm install

# Run development server
npm run dev

# Type check
npm run type-check

# Run tests
npm test
```

### Infrastructure (Docker)

```bash
# Start all services
docker compose -f infra/docker-compose.yml --env-file .env up --build

# View logs
docker compose -f infra/docker-compose.yml logs -f
```

## Architecture Notes

### Two-Phase Pipeline

1. **Initial Pass**: High-recall screening using classical ML (ELA, JPEG Ghost, SIFT, CLIP)
2. **Deep Pass**: High-precision investigation using 2026-era detectors (Diffusion Artifacts, Inter-frame Forgery, C2PA JUMBF)
3. **Semantic Grounding**: Suspicious findings are grounded via Gemini 2.0 Flash Vision

### HITL (Human-in-the-Loop)

The pipeline can pause for human decisions between Initial and Deep passes. WebSocket events (`PIPELINE_PAUSED`, `HITL_CHECKPOINT`) notify the frontend.

### ReAct Loop

Agents use either:
- **Task-decomposition driver** (default): Fast iteration through predefined tasks
- **LLM driver** (optional): Groq-powered reasoning for richer traces

### Chain of Custody

Every tool execution is logged to PostgreSQL via `CustodyLogger` with ECDSA P-256 cryptographic signing.

### Manipulation Probability Calculation

The Arbiter computes `manipulation_probability` using reliability-weighted signals:
- Single signal: `confidence × reliability_weight × 0.55`
- Multiple signals: weighted average of top-7 signals + volume bonus

## Import Conventions

### Storage Abstraction

Use `@/lib/storage` for all non-auth storage. This wraps `localStorage` and dispatches events for cross-tab synchronization.

**Exception**: Auth tokens in `@/lib/api.ts` intentionally use `sessionStorage` because JWT bearer tokens expire with the browser session. The primary auth flow uses HttpOnly cookies.

```typescript
import { storage } from "@/lib/storage";

// Write
storage.setItem("my_key", someObject, true);

// Read
const value = storage.getItem<MyType>("my_key", true);
```

### Backend Imports

```python
from core.persistence.evidence_store import EvidenceStore  # Correct
from infra.persistence.evidence_store import EvidenceStore  # Legacy - avoid
```

## Coding Conventions

### Backend (Python)

- **Strict typing**: Always use type hints
- **No LLM verdict-setting**: Verdicts are computed deterministically from structured evidence; LLMs only generate summaries
- **Logging**: Use `get_logger(__name__)` for structured logging
- **Custody logging**: Log significant actions to `CustodyLogger`

### Frontend (TypeScript/React)

- **Component structure**: Use `use client` for components needing browser APIs
- **State management**: Use React hooks (`useState`, `useEffect`, `useCallback`)
- **Types**: Define interfaces in `@/types` or near their usage

## Agent Guidelines

### GSD Workflow

1. Check `docs/STATE.md` for active tasks and blockers
2. Run lint/typecheck before committing
3. Test changes with `docker compose up --build`

### Arbiter Verdict Logic

**Never modify Arbiter verdict logic without understanding**:
- The `manipulation_probability` formula uses reliability weights per tool
- The `_TOOL_RELIABILITY_TIERS` dictionary maps tools to weights (0.5–1.0)
- Verdict thresholds are deterministic: AUTHENTIC, LIKELY_AUTHENTIC, INCONCLUSIVE, SUSPICIOUS, LIKELY_MANIPULATED, MANIPULATED, ABSTAIN

### Context Injection

- Agent 1 (Image) injects Gemini context into Agents 3 and 5 via `inject_agent1_context()`
- Agents 3 and 5 delay deep-pass execution until receiving `agent1_complete` signal
