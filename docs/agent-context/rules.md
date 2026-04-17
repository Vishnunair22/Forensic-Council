# Forensic Council — Rules for Making Changes

These rules exist to protect the legal defensibility of investigations and the integrity of the codebase.

---

## Non-Negotiable Rules

### 1. Never Bypass the Custody Logger
Every forensic analysis step, tool call, agent decision, and HITL action MUST be logged through `CustodyLogger` (apps/api/core/custody_logger.py). This creates the court-admissible chain of custody. Adding analysis logic outside the custody chain makes findings legally indefensible.

### 2. Never Weaken Cryptographic Signing
- All custody entries must be ECDSA P-256 signed
- Report signatures must be verifiable against the stored public key
- Do not downgrade to weaker algorithms (MD5/SHA1 hashing, RSA-1024)
- Do not disable signature verification checks

### 3. Never Add Insecure Defaults
`core/config.py` blocks weak passwords and placeholder keys in production. Do not:
- Add new config values with insecure defaults that bypass the existing checks
- Disable the `SIGNING_KEY` validation
- Add hardcoded credentials anywhere in the codebase

### 4. Always Keep Changes Async (Backend)
The entire backend is async. Never introduce:
- Synchronous database calls (use asyncpg, not psycopg2)
- Synchronous HTTP calls (use httpx.AsyncClient, not requests)
- `time.sleep()` in async code (use `await asyncio.sleep()`)

### 5. Never Call Agent Tools Directly — Use ToolRegistry
All forensic tools must be invoked through `ToolRegistry` (core/tool_registry.py). Direct tool calls bypass custody logging and error handling.

### 6. Never Store Sensitive Data in localStorage
Frontend auth tokens and session data use `sessionStorage` (clears on browser close). This is intentional for security. Do not migrate to `localStorage`.

---

## Frontend Rules

### Design System Consistency
- **Palette:** Indigo-600 (primary), Slate-50/950 (backgrounds), Slate-200/800 (borders)
- **Fonts:** Syne for display text, JetBrains Mono for code/technical
- **No neon colors** — the CyberNoir design was replaced in v1.1.1
- **Agent badges:** Transparent backgrounds with text color (not solid fills)

### Image Rendering
- Use native `<img>` for base64 data URLs (upload previews, report images)
- Use Next.js `<Image>` only for static assets and remote URLs with configured domains
- Never switch upload preview from native `<img>` to `<Image>` — it will break

### State Management
- Add new investigation state to `useForensicData` hook, not scattered local state
- All API calls go through `lib/api.ts` — do not add fetch/axios calls inline in components
- WebSocket handling lives in `api.ts:startLiveStream` — don't create additional WebSocket connections

### TypeScript
- All API response types must have corresponding TypeScript interfaces in `lib/api.ts` or `types/index.ts`
- Use Zod schemas in `lib/schemas.ts` for runtime validation of external data
- No `any` types for API data (defeat the purpose of the type system)

---

## Backend Rules

### New Agent Tools
When adding a new forensic tool:
1. Implement in `apps/api/tools/` (or `apps/api/tools/ml_tools/` for ML-based tools)
2. Register in the agent's `_build_tool_registry()` method
3. Add custody logging for tool execution and result
4. Add unit tests in `apps/api/tests/unit/`
5. Document the tool's output schema in a docstring

### New API Endpoints
When adding a new route:
1. Create Pydantic models in `apps/api/api/schemas.py` for request/response
2. Add to the appropriate router in `apps/api/api/routes/`
3. Add JWT auth dependency unless the endpoint is explicitly public
4. Add integration test in `apps/api/tests/integration/test_api_routes.py`
5. Update the API surface table in `agent-context/project_context.md`

### New Agent Types
If adding a 6th agent or specialization:
1. Inherit from `BaseAgent` (apps/api/agents/base_agent.py)
2. Implement `task_decomposition()` and `deep_task_decomposition()`
3. Register with the pipeline in `orchestration/pipeline.py`
4. Add to the arbiter's agent list in `agents/arbiter.py`
5. Add frontend card in landing page agent showcase (`app/page.tsx`)
6. Add agent ID to constants (`apps/web/src/lib/constants.ts`)

### Database Schema Changes
- Add migrations to `apps/api/core/migrations.py`
- Never drop or rename columns in existing tables (break chain of custody queries)
- New columns should be nullable or have defaults (don't break existing rows)
- Test schema changes with `scripts/init_db.py`

### LLM Client Changes
`core/llm_client.py` is the unified LLM client (Groq/OpenAI/Anthropic). Changes here affect ALL agents. Test changes with all three providers if possible. The fallback behavior (`LLM_PROVIDER=none`) must continue to work — agents must degrade gracefully to task-driven mode.

---

## Testing Rules

### Required Before Merging
- New Python code: unit test in `apps/api/tests/unit/`
- New API route: integration test in `apps/api/tests/integration/`
- New security-relevant code: test in `apps/api/tests/security/`
- New frontend hook/utility: Jest test

### Test Commands
```bash
# Backend (all non-connectivity tests)
pytest tests/ --ignore=tests/connectivity -v

# Backend (specific)
pytest apps/api/tests/unit/ -v

# Frontend
cd apps/web && npm test -- --watchAll=false

# Connectivity (requires running Docker stack)
pytest tests/connectivity/ -v
```

### Don't Mock the Database in Integration Tests
Use real PostgreSQL and Redis in integration tests (provided via conftest.py fixtures). Mocking the DB has caused failures to slip through in the past (mock/prod divergence on schema queries).

---

## When Modifying These Context Files

Update `agent-context/project_context.md` when:
- Adding new agents
- Adding new API endpoints
- Changing the tech stack
- Adding new environment variables
- Changing the deployment process

Update `agent-context/memory.md` when:
- An architectural decision is made (document the "why")
- A bug is fixed that involved a non-obvious root cause
- A pattern is established or changed
- A known issue is discovered or resolved

Update `agent-context/rules.md` when:
- A new constraint is established (new security requirement, legal requirement)
- A rule is changed or relaxed with explicit justification
- A new category of code is added that needs rules

---

## Git Workflow

- Branch from `main`
- Commit messages: conventional commits format (`feat:`, `fix:`, `security:`, `docs:`, `refactor:`, `test:`)
- Don't skip pre-commit hooks (`--no-verify`)
- Don't force-push to `main`
- Don't commit `.env` files, API keys, or any credentials
- Run `pytest tests/ --ignore=tests/connectivity -v` before opening a PR






