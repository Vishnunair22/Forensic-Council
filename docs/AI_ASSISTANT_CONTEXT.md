# AI Assistant Context & Guidelines

Welcome, Agent. This project follows a specific monorepo and architectural pattern optimized for high-integrity forensic analysis.

## Monorepo Structure

- `apps/api`: Python (FastAPI) backend orchestrating the multi-agent tribunal.
- `apps/web`: Next.js frontend for investigator interaction and visualization.
- `infra/`: System-level infrastructure (Docker Compose, Caddy, deployment scripts).
- `docs/`: Central documentation and audit logs.

## Backend Architecture (apps/api)

- `agents/`: The "Tribunal". Contains the logic for the 5 specialized forensic agents and the Arbiter.
- `core/`:
  - `persistence/`: Database clients and storage handlers (formerly `infra`).
  - `orchestration/`: The `pipeline.py` and `SignalBus` logic.
  - `forensics/`: Specialized logic for SIFT, ELA, and other signal processing.
- `api/`: FastAPI routes, schemas, and entry points.

## Coding Standards

1.  **Strict Typing**: Always use Python type hints and TypeScript interfaces.
2.  **Forensic Integrity**: Every significant thought or action should be logged via the `custody_logger`.
3.  **Imports**: 
    - In `api`: Use `from core.persistence...` instead of the legacy `from infra...`.
    - Always use relative imports within components where appropriate, but prefer absolute imports from the app root (`api`, `core`, etc.) for clarity.
4.  **No Junk**: Do not create temporary files in the root. Use `apps/api/scratch/` or `apps/web/public/temp/` if absolutely necessary, but ensure they are ignored by git.

## Environment Variables

Standardized root `.env` is the single source of truth for both service and infrastructure configuration.

---
*Note: This file is intended to provide immediate context for any AI assistant joining the project session map.*

