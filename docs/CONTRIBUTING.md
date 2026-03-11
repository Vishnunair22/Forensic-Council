# Contributing to the Forensic Council

Thank you for your interest in contributing to the Forensic Council system! This document outlines our standard workflow for branching, committing, testing, and reviewing code.

## 1. Development Workflow

We use a standard Feature-Branch workflow.
1. **Never commit directly to `main`**.
2. **Sync your fork** before creating a new branch.
3. **Branch naming**: Use the format `type/issue-number-description` or `type/description`.
   - Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.
   - Examples: `feat/123-audio-splice-detector`, `fix/redis-memory-leak`, `docs/update-api`.

## 2. Commit Message Format

Commit messages should be precise. We loosely follow Conventional Commits.

*   `feat: add IsolationForest routing for deepfakes`
*   `fix(api): catch AttributeError on literal property evaluation`
*   `docs: document HITL webhook structure`

## 3. Pull Request Process

When generating a PR, adhere to the following checklist:
1. **Run Tests Offline:** Ensure `pytest` and `npm test` execute successfully locally. See `TESTING.md`.
2. **Linting & Formatting:**
   - Backend: Run `uv run ruff check .` and `uv run ruff format --check .`.
   - Frontend: Run `npm run lint` and `npx tsc --noEmit`.
3. **Draft the PR:** Attach screenshots/videos if UI changes are involved. Describe the **problem** and the **solution**.
4. **Code Review Expectations:**
   - A minimum of 1 approval is required for non-critical changes.
   - Changes to the cryptographic signing methodology (`core/signing.py`) require 2 senior approvals.

## 4. CI/CD Pipeline

All PRs and pushes to `main`/`develop` run `.github/workflows/ci.yml` automatically. The pipeline covers:

| Job | What it checks |
|-----|----------------|
| `backend-test` | `ruff` lint + format, Pyright types, `pytest tests/unit/` with coverage |
| `backend-docker` | Production Docker build (`target: production`) |
| `frontend-test` | ESLint, TypeScript type-check, `next build` |
| `frontend-docker` | Production Docker build (`target: runner`) |
| `security-audit` | `pip-audit` (Python) + `npm audit --audit-level=high` |
| `integration-smoke` | Full stack smoke test on `main` pushes: `/health` + auth rejection |

PRs that fail any non-advisory job are blocked from merge.

## 5. Setting up the Development Environment

Please consult the root [`README.md`](../README.md) and [`docs/docker/DOCKER_BUILD.md`](docker/DOCKER_BUILD.md) to spin up the local Docker environment.

**Linux / macOS** — use the provided shell script:
```bash
./manage.sh dev      # hot-reload dev stack
./manage.sh logs     # tail all container logs
./manage.sh down     # stop (keeps volumes)
```

**Windows (PowerShell):**
```powershell
.\manage.ps1 dev
.\manage.ps1 logs
.\manage.ps1 down
```

Both scripts are functionally identical. See the root `README.md` for the full command reference.
