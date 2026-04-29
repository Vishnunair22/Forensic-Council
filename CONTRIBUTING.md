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
*   `chore: update .env.example with CHANGE_ME placeholders`

**Scope prefixes** (optional but encouraged):
- `api:` — API route or middleware changes
- `agent:` — Agent logic changes
- `ui:` — Frontend component changes
- `infra:` — Docker, compose, or infrastructure changes
- `security:` — Auth, signing, or security-related changes

## 3. Code Style

All functions, classes, and modules must have Google-style docstrings with type annotations.

```python
def process_image(image_path: str, threshold: float = 0.5) -> Dict[str, Any]:
    """
    Process an image for forensic analysis.

    Args:
        image_path: Path to image file on disk
        threshold: Confidence threshold (0.0-1.0) for flagging anomalies

    Returns:
        Dictionary with keys:
            - "status": "success" or "error"
            - "findings": List of forensic findings
            - "confidence": Overall confidence 0-1

    Raises:
        FileNotFoundError: If image_path doesn't exist
    """
```

**Linting Rules**:
- Backend: `ruff` (linting + formatting)
- Frontend: ESLint + TypeScript
- No unused imports or variables
- No print statements in production code (use logger instead)

## 4. Pull Request Process

When generating a PR, adhere to the following checklist:
1. **Run Tests Offline:** Ensure `pytest` and `npm test` execute successfully locally.
2. **Linting & Formatting:**
   - Backend: Run `uv run ruff check .` and `uv run ruff format --check .`.
   - Frontend: Run `npm run lint` and `npx tsc --noEmit`.
3. **Draft the PR:** Attach screenshots/videos if UI changes are involved. Describe the **problem** and the **solution**.
4. **Code Review Expectations:**
   - A minimum of 1 approval is required for non-critical changes.
   - Changes to the cryptographic signing methodology (`core/signing.py`) require 2 senior approvals.

## 5. CI/CD Pipeline

All PRs and pushes to `main`/`develop` run CI automatically:

| Job | What it checks |
|-----|----------------|
| `backend-test` | `ruff` lint + format, Pyright types, `pytest tests/unit/` with coverage |
| `frontend-test` | ESLint, TypeScript type-check, `next build` |
| `security-audit` | `pip-audit` (Python) + `npm audit --audit-level=high` |

PRs that fail any non-advisory job are blocked from merge.

## 6. Pull Request Checklist

Before requesting review, verify:

- [ ] All tests pass locally (`pytest` for backend, `npm test` for frontend)
- [ ] Linting passes (`ruff check .` for backend, `npm run lint` for frontend)
- [ ] TypeScript compiles without errors (`npx tsc --noEmit`)
- [ ] Docker builds succeed (`docker compose build`)
- [ ] No `CHANGE_ME` placeholders left in `.env` (if adding new secrets)
- [ ] Documentation updated for user-facing changes
- [ ] Security implications considered (auth, data exposure, injection)
- [ ] New `.env` vars documented in `.env.example`
- [ ] Database schema changes include migration scripts

**For security-sensitive changes** (auth, signing, data handling):
- [ ] Threat model documented in PR description
- [ ] Security review requested from team lead
- [ ] Regression tests added for security boundaries
- [ ] Reviewed by 2 senior maintainers

## 7. Code of Conduct

We are committed to a welcoming and inclusive environment. Please refer to [Contributor Covenant Code of Conduct v2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).

## 8. Setting up the Development Environment

Please consult the root [`README.md`](README.md) for local Docker setup instructions.

**Linux / macOS:**
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