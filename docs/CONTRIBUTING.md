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
   - Backend: Use `ruff` for both linting and formatting.
   - Frontend: Run `npm run lint`.
3. **Draft the PR:** Attach screenshots/videos if UI changes are involved. Describe the **problem** and the **solution**.
4. **Code Review Expectations:** 
   - A minimum of 1 approval is required for non-critical changes. 
   - Changes to the cryptographic signing methodology (`core/signing.py`) require 2 senior approvals.

## 4. Setting up the Development Environment

Please consult the root [`README.md`](../README.md) and [`docs/docker/DOCKER_BUILD.md`](docker/DOCKER_BUILD.md) to spin up the local Docker environment, including Qdrant, Redis, Postgres, the API subsystem, and the Next.js frontend.
