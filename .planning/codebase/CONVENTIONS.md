# Coding Conventions

**Analysis Date:** 2026-04-17 (Post-Audit Refresh)

## Naming Patterns

**Files (Python):**
- `snake_case.py` for all modules: `custody_logger.py`, `react_loop.py`, `working_memory.py`
- Test files: `test_<module_name>.py` — `test_arbiter_unit.py`, `test_signing_unit.py`
- Private route helpers: `_rate_limiting.py`, `_session_state.py` (leading underscore)

**Files (TypeScript):**
- `PascalCase.tsx` for React components: `UploadModal.tsx`, `AgentProgressDisplay.tsx`
- `camelCase.ts` for non-component modules: `storage.ts`, `api.ts`, `schemas.ts`
- `useHookName.ts` for custom hooks: `useInvestigation.ts`, `useSimulation.ts`

**Functions (Python):**
- `snake_case` for all functions and methods: `get_logger`, `sign_content`, `verify_entry`
- `_leading_underscore` for internal helpers: `_make_finding()`, `_attach_llm_reasoning_to_findings()`
- Async functions are named identically to sync — context determines async usage

**Functions (TypeScript):**
- `camelCase` for functions and hooks: `startInvestigation`, `withTimeout`, `waitForFinalReport`
- `PascalCase` for React components: `UploadModal`, `AgentProgressDisplay`
- `_leading_underscore` for private module-internal helpers: `_parseReportDTO`

**Variables:**
- Python: `snake_case` throughout; module-level constants `ALL_CAPS_SNAKE`: `INSECURE_DEFAULTS`
- TypeScript: `camelCase`; top-level constants `SCREAMING_SNAKE_CASE`: `INVESTIGATION_REQUEST_TIMEOUT_MS`, `ALLOWED_MIME_TYPES`

**Types / Interfaces (TypeScript):**
- `PascalCase` interfaces defined near usage or in `@/types`: `UploadModalProps`, `AgentUpdate`, `FindingPreview`
- Zod schemas named `<Entity>Schema`: `ReportDTOSchema`, `AgentResultSchema`
- Type imports use `type` keyword: `import { type HITLCheckpoint, type ArbiterStatusResponse }`

**Classes (Python):**
- `PascalCase`: `ForensicCouncilBaseException`, `CouncilArbiter`, `CustodyLogger`
- Exception classes end with `Error` or `Exception`: `CircuitBreakerOpen`, `ToolUnavailableError`
- Enums use `PascalCase` class with `UPPER_CASE` values; `StrEnum` preferred: `EntryType(StrEnum)`

## Code Style

**Formatting (Python):**
- Ruff enforces line length: 100 characters (configured in `apps/api/pyproject.toml`)
- Target Python version: 3.12
- isort profile: `black`, `multi_line_output = 3`, line length 100

**Formatting (TypeScript):**
- No Prettier config detected — formatting enforced via ESLint
- ESLint extends `next/core-web-vitals` and `next/typescript` (flat config in `apps/web/eslint.config.mjs`)
- `prefer-const: error` enforced

**Linting (Python):**
- Ruff rule sets: `E`, `F`, `W`, `I` (imports), `N` (naming), `UP` (pyupgrade), `S` (security), `B` (bugbear), `A`, `C4`, `PT` (pytest)
- Ignored: `E501` (line length — handled separately), `S101` (assert in tests)
- Run: `cd apps/api && uv run ruff check .`

**Linting (TypeScript):**
- `@typescript-eslint/no-unused-vars: error` (args/vars with `_` prefix are allowed)
- `@typescript-eslint/no-explicit-any: warn`
- `@typescript-eslint/no-non-null-assertion: error`
- `react-hooks/exhaustive-deps: error`
- `@next/next/no-img-element: error` — always use Next.js `<Image>` instead
- `jsx-a11y/alt-text: error`, `jsx-a11y/aria-props: error`, `jsx-a11y/role-has-required-aria-props: error`
- Run: `cd apps/web && npm run lint` (zero warnings allowed: `--max-warnings 0`)

**TypeScript Strictness:**
- `strict: true` in `apps/web/tsconfig.json` (no `any` without justification)
- Target: `ES2020`, module resolution: `bundler`
- `noEmit: true` — type-check only, no build output

**Python Type Checking:**
- Pyright in `basic` mode for most modules
- `strict` mode enforced on critical security modules: `core/auth.py`, `core/signing.py`, `core/circuit_breaker.py`
- Run: `cd apps/api && uv run pyright core/ agents/ api/`

## Import Organization

**Python Order (enforced by ruff `I` + isort):**
1. Standard library: `import asyncio`, `from typing import Any`
2. Third-party: `from fastapi import ...`, `from pydantic import ...`
3. Local project (with blank line separator): `from core.config import get_settings`

**TypeScript Order (convention observed in source):**
1. React and Next.js: `import { useState, useCallback } from "react"`
2. Third-party: `import { motion } from "framer-motion"`
3. Internal `@/` path aliases: `import { storage } from "@/lib/storage"`
4. Relative imports last

**Path Aliases (TypeScript):**
- `@/*` maps to `apps/web/src/*` (configured in `apps/web/tsconfig.json`)
- Use `@/lib/storage`, `@/hooks/useSimulation`, `@/components/evidence/UploadModal` — never relative paths across feature boundaries

**Python Import Convention:**
- Correct: `from core.persistence.evidence_store import EvidenceStore`
- Legacy/avoid: `from infra.persistence.evidence_store import EvidenceStore`

## Storage Abstraction (Frontend)

**Rule:** Use `@/lib/storage` for all non-auth browser storage. The abstraction wraps `localStorage`/`sessionStorage` and dispatches `fc_storage_update` custom events for cross-tab sync.

```typescript
// Import
import { storage, sessionOnlyStorage } from "@/lib/storage";

// Write — always pass stringify=true for objects
storage.setItem("my_key", someObject, true);

// Read — always pass parseJson=true for objects
const value = storage.getItem<MyType>("my_key", true);

// Session-scoped (clears with browser session)
sessionOnlyStorage.setItem("session_key", value);
```

**Exception:** Auth tokens in `apps/web/src/lib/api.ts` intentionally use raw `sessionStorage` because JWT bearer tokens expire with the browser session. The primary auth flow uses HttpOnly cookies.

## Error Handling

**Python:**
- All custom exceptions inherit from `ForensicCouncilBaseException` (defined in `apps/api/core/exceptions.py`)
- Exception hierarchy: `ForensicCouncilBaseException` → domain base (e.g. `InfrastructureError`) → specific (e.g. `DatabaseConnectionError`)
- **Explicit Exception Handling:** Avoid bare `except:` blocks. Always use `except Exception:` (or more specific) and log the error context to prevent swallowing system signals.
- `ToolUnavailableError` must never crash the system — catch it and log an `INCOMPLETE` finding
- Exceptions carry `message`, `error_code`, and `details` dict; serializable via `.to_dict()`
- FastAPI route handlers raise `HTTPException` with explicit status codes; never let raw exceptions propagate

**TypeScript:**
- API client uses `try/catch` around `fetch` calls; failed responses log via `dbg.warn` (silenced in production)
- Schema validation failures in `_parseReportDTO` fall back gracefully (`return raw as ReportDTO`) — never silently break UI
- Storage errors are caught and logged via `console.warn` with key context; never throw from storage operations

## Logging

**Python Framework:** `StructuredLogger` / `get_logger` from `core.structured_logging` (re-exported via `core.logging` shim)

**Usage Pattern:**
```python
from core.structured_logging import get_logger

logger = get_logger(__name__)  # Module-level, always use __name__

# Structured key=value args — NOT string interpolation
logger.info("Starting investigation", session_id=session_id, env=settings.app_env)
logger.error("Production validation failed", error=str(e))
```

- Logs output as JSON with `timestamp`, `level`, `logger`, `message`, and extra fields
- Sensitive keys (`password`, `secret`, `key`, `token`, `auth`, `credential`, `private`, `signing`) are automatically masked as `"********"`
- `request_id_ctx` context var is included in every log line when set

**TypeScript:**
- Dev-only logger in `apps/web/src/lib/api.ts`: `dbg.log/warn/error` — silenced when `NODE_ENV === "production"`
- `console.warn` for storage errors with key context prefix: `[storage] Error reading key "...":`
- No third-party logging library on the frontend

## Comments

**Python:**
- Module docstrings required: triple-quoted with title, separator line (`=`), and description
- Class docstrings required with `Attributes:` section for models
- Function docstrings for public API: `Args:` and `Returns:` blocks
- Inline comments used sparingly for non-obvious logic (e.g. dependency resolution notes in `pyproject.toml`)
- Section dividers using `# ── Section Name ────────...` pattern

**TypeScript:**
- JSDoc-style block comments (`/** ... */`) for module-level documentation and complex functions
- Inline `//` comments for business logic rationale (e.g. CORS fix, WebSocket origin reasons)
- `@ts-ignore` allowed only with explicit justification comment immediately above

## Function Design

**Python:**
- Async functions used throughout for I/O-bound operations (`async def`, `await`)
- Factory functions named `_make_<thing>()` in test files (private to test module)
- `@lru_cache` for singleton settings: `get_settings()` in `core/config.py`
- `@classmethod` for validators in Pydantic models: `@field_validator` with `@classmethod`

**TypeScript:**
- Hooks return plain objects (not arrays) with named properties: `{ status, agentUpdates, connectWebSocket, ... }`
- `useCallback` wraps all event handlers passed as props to prevent unnecessary re-renders
- Utility functions placed in `apps/web/src/lib/utils.ts`; domain helpers near usage

## Module Design

**Python:**
- `__init__.py` files mark packages but are mostly empty
- `__all__` used in shim/re-export modules to enumerate public names: `core/logging.py`
- Pydantic `BaseModel` for all data models; `BaseSettings` for configuration

**TypeScript Exports:**
- Named exports preferred over default exports for components and utilities
- Barrel file exists: `apps/web/src/components/ui/index.ts`
- `"use client"` directive at top of any component using browser APIs or hooks

## Agent-Specific Rules

- **No LLM verdict-setting:** Verdicts are computed deterministically from structured evidence. LLMs only generate text summaries.
- **Custody logging:** All significant forensic actions must be logged via `CustodyLogger` with appropriate `EntryType`
- **Context injection:** Agent 1 injects Gemini context into Agents 3 and 5 via `inject_agent1_context()`; never call deep-pass directly without checking `agent1_complete` signal

---

*Convention analysis: 2026-04-17*
