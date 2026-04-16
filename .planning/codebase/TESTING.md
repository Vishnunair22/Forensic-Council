# Testing Patterns

**Analysis Date:** 2026-04-16

## Backend Test Framework

**Runner:**
- pytest 8.4+ with pytest-asyncio 1.0+
- Config: `apps/api/pyproject.toml` (`[tool.pytest.ini_options]`)

**Assertion Library:**
- Standard `assert` statements (ruff `S101` ignored in tests)

**Key Plugins:**
- `pytest-asyncio` — `asyncio_mode = "auto"` (no `@pytest.mark.asyncio` decorator needed on most tests)
- `pytest-cov` — coverage collection during test runs
- `pytest-mock` — `mocker` fixture for mocking
- `faker` and `factory-boy` — test data generation

**Run Commands:**
```bash
cd apps/api

# Run all tests
uv run pytest tests/ -v --tb=short

# Run with coverage
uv run pytest tests/ --cov

# Run only unit tests
uv run pytest tests/unit/ -v

# Run only integration tests
uv run pytest tests/integration/ -v

# Run with marker filter
uv run pytest -m "unit" -v
uv run pytest -m "not slow and not requires_docker" -v
```

## Backend Test File Organization

**Location:**
- `apps/api/tests/unit/` — pure unit tests (no infrastructure)
- `apps/api/tests/integration/` — API route and pipeline integration tests
- Top-level `tests/` — system-level and cross-service tests (fixtures, backend, e2e, connectivity)

**Naming:**
- `test_<module_name>_unit.py` for granular unit tests: `test_arbiter_unit.py`, `test_signing_unit.py`
- `test_<module_name>.py` for broader coverage: `test_working_memory.py`, `test_forensic_tools.py`
- Integration tests: `test_api_routes.py`, `test_pipeline_e2e.py`

**conftest.py:**
- `apps/api/tests/integration/conftest.py` — sets `sys.path` to guarantee `apps/api/` is the package root

## Backend Test Structure

**Suite Organization:**
```python
# Always set env vars BEFORE imports at top of test file
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SIGNING_KEY", "test-signing-key-" + "x" * 32)
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_PASSWORD", "test")
os.environ.setdefault("NEXT_PUBLIC_DEMO_PASSWORD", "test")
os.environ.setdefault("LLM_PROVIDER", "none")
os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_MODEL", "test-model")

# Then import project modules
from core.signing import AgentKeyPair, sign_content

# Test classes group by subject, named Test<Subject>
class TestSignedEntry:
    def test_creation(self): ...
    def test_to_dict(self): ...
    def test_from_dict_roundtrip(self): ...

class TestAgentKeyPair:
    def test_generate_random(self): ...

# Section dividers using ── SectionName ──────────── comments
```

**Env Setup Pattern:**
Every unit test file begins with `os.environ.setdefault(...)` calls before any project imports. This prevents `Settings` validation failures when `pydantic-settings` reads the environment at import time. The standard required set is shown above.

## Backend Mocking

**Framework:** `unittest.mock` (`AsyncMock`, `MagicMock`, `patch`) — standard library only

**Infrastructure Mocking Pattern (Integration Tests):**
```python
@pytest.fixture(scope="module")
def client():
    """Return a TestClient with DB / Redis / Qdrant fully mocked."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)

    mock_pg = AsyncMock()
    mock_pg.fetch_one = AsyncMock(return_value=None)
    mock_pg.fetch_all = AsyncMock(return_value=[])

    patches = [
        patch("core.persistence.redis_client.get_redis_client", return_value=mock_redis),
        patch("core.persistence.postgres_client.get_postgres_client", return_value=mock_pg),
        patch("core.persistence.qdrant_client.get_qdrant_client", return_value=mock_qdrant),
        patch("core.migrations.run_migrations", new_callable=AsyncMock),
    ]
    # Start all patches, yield TestClient, stop all patches in finally
```

**Factory Helpers in Unit Tests:**
```python
def _make_finding(agent_id="Agent1", finding_type="ela", status="CONFIRMED", confidence=0.85, **kwargs) -> dict:
    """Private factory function for test data — prefix with underscore."""
    return {
        "agent_id": agent_id,
        "finding_type": finding_type,
        "confidence_raw": confidence,
        ...
        **kwargs,
    }

def _make_arbiter(session_id=None) -> CouncilArbiter:
    from core.config import Settings
    config = Settings(app_env="testing", signing_key="test-signing-key-" + "x" * 32, ...)
    cl = AsyncMock()
    cl.log_entry = AsyncMock()
    ...
```

**What to Mock:**
- All infrastructure clients: Redis, PostgreSQL, Qdrant
- LLM providers (Groq, Gemini) — set `LLM_PROVIDER=none` via env
- External HTTP calls via `patch("httpx.AsyncClient.get", ...)`
- DB migrations and bootstrap scripts

**What NOT to Mock:**
- The subject under test (business logic in `core/`, `agents/`, `orchestration/`)
- Pydantic models and data validation
- Cryptographic signing logic in `core/signing.py`

## Backend Test Markers

Defined in `apps/api/pyproject.toml`:
```
unit            — pure unit tests, no infrastructure
integration     — requires mocked or real infrastructure
regression      — regression coverage for known bugs
requires_docker — requires a running Docker stack
requires_network — requires internet access
slow            — long-running tests
```

Use `pytest.mark.skipif` for conditional skips:
```python
pytestmark = pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
```

## Backend Coverage

**Requirements:** 60% line coverage minimum (`fail_under = 60` in both pytest and coverage config)

**Source tracked:** `core`, `agents`, `tools`, `orchestration`

**Omitted from coverage:**
- `tools/ml_tools/*.py` (GPU-dependent ML code)
- `*/worker.py`
- `*/model_cache.py`

**Excluded lines:**
- `pragma: no cover`
- `def __repr__`
- `raise NotImplementedError`
- `if __name__ == "__main__":`
- `if TYPE_CHECKING:`
- `...` (ellipsis / abstract stubs)

---

## Frontend Test Framework

**Runner:**
- Jest 30+ with `jest-environment-jsdom`
- Config: `apps/web/jest.config.ts`
- Setup: `apps/web/jest.setup.ts`

**Assertion Library:**
- `@testing-library/jest-dom` — DOM assertions (`toBeInTheDocument`, `toBeDisabled`, etc.)
- `jest-axe` — accessibility violation assertions (`toHaveNoViolations`)

**Run Commands:**
```bash
cd apps/web

# Run all tests
npm test                # jest --passWithNoTests

# Watch mode
npm run test:watch      # jest --watch

# Coverage
npm run test:coverage   # jest --coverage

# Type check (separate from tests)
npm run type-check      # tsc --noEmit --incremental false
```

## Frontend Test File Organization

**Location:**
- `apps/web/tests/unit/hooks/` — hook unit tests: `useInvestigation.test.ts`, `useSimulation.test.ts`
- `apps/web/tests/unit/lib/` — library unit tests: `api.test.ts`, `schemas_utils.test.ts`, `sse.test.ts`
- `apps/web/tests/unit/app/` — Next.js route handler tests: `routes.test.ts`, `session-expired.test.tsx`
- `apps/web/tests/accessibility/` — WCAG 2.1 AA tests: `accessibility.test.tsx`, `pages.test.tsx`
- `apps/web/tests/e2e/` — Playwright E2E: `browser_journey.spec.ts`, `websocket_flow.test.ts`
- Root-level: `tests/components.test.tsx`, `tests/storage.test.ts`, `tests/useSimulation.test.ts`

**Naming:**
- `*.test.ts` / `*.test.tsx` for Jest
- `*.spec.ts` for Playwright E2E

## Frontend Test Structure

**Jest — Component Tests:**
```typescript
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MyComponent } from "@/components/...";

// framer-motion must ALWAYS be mocked (motion requires real DOM scroll context)
jest.mock("framer-motion", () => ({
  motion: new Proxy({}, {
    get: (_t, tag: string) => ({ children, ...props }) =>
      React.createElement(tag, { ...stripMotionProps(props) }, children),
  }),
  AnimatePresence: ({ children }) => <>{children}</>,
  useScroll: () => ({ scrollYProgress: { get: () => 0 } }),
  useTransform: (_, __, output) => ({ get: () => output[0] }),
}));

describe("MyComponent", () => {
  beforeEach(() => jest.clearAllMocks());

  it("renders expected text", () => {
    render(<MyComponent prop={value} />);
    expect(screen.getByText(/expected text/i)).toBeInTheDocument();
  });
});
```

**Jest — Hook Tests:**
```typescript
import { renderHook, act } from "@testing-library/react";
import { useMyHook } from "@/hooks/useMyHook";

describe("useMyHook", () => {
  it("initialises with idle status", () => {
    const { result } = renderHook(() => useMyHook({}));
    expect(result.current.status).toBe("idle");
  });
});
```

**Next.js Route Handler Tests:**
```typescript
/** @jest-environment node */  // Required for route handlers

jest.mock("@/lib/backendTargets", () => ({ ... }));

describe("app api routes", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    global.fetch = jest.fn();
  });

  it("route returns expected response", async () => {
    const { POST } = await import("@/app/api/auth/demo/route");  // dynamic import
    (global.fetch as jest.Mock).mockResolvedValue({ ok: true, json: async () => ({}) });
    const response = await POST();
    expect(response.status).toBe(200);
  });
});
```

## Frontend Mocking

**Global mocks in `jest.setup.ts` (applied to all tests):**
- `framer-motion` — full mock with Proxy-based `motion.*` passthrough
- `@/hooks/useSound` — `playSound: jest.fn()`
- `window.scrollTo` and `global.scrollTo` — `jest.fn()`
- `window.matchMedia` — mock implementation returning `{ matches: false, ... }`

**Per-test mocks:**
```typescript
// Mock Next.js router
jest.mock("next/navigation", () => ({
  useRouter: jest.fn(),
}));
(useRouter as jest.Mock).mockReturnValue({ push: mockPush });

// Mock entire API module but keep real implementations
jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  startInvestigation: jest.fn(),
  getReport: jest.fn(),
}));

// Mock sessionStorage
Object.defineProperty(window, "sessionStorage", {
  value: { getItem: jest.fn(), setItem: jest.fn(), removeItem: jest.fn() },
  writable: true,
});

// Mock WebSocket
global.WebSocket = jest.fn().mockImplementation(() => ({
  send: jest.fn(), close: jest.fn(),
  addEventListener: jest.fn(), removeEventListener: jest.fn(),
  readyState: 0,
})) as unknown as typeof WebSocket;

// Mock URL APIs
window.URL.createObjectURL = jest.fn(() => "mock-url");
window.URL.revokeObjectURL = jest.fn();
```

**Mock fetch pattern (api.test.ts):**
```typescript
const mockResponses: Response[] = [];
global.fetch = jest.fn((url) => {
  if (url.includes('/api/v1/health')) {
    return Promise.resolve({ ok: true, status: 200, json: async () => ({}) } as Response);
  }
  const response = mockResponses.shift();
  return Promise.resolve(response ?? { ok: true, status: 200, json: async () => ({}) } as Response);
});

function respondJson(body: unknown, status = 200) {
  mockResponses.push({ ok: status < 400, status, json: async () => body } as Response);
}
```

## Frontend Coverage

**Requirements:** 60% global line coverage (`coverageThreshold: { global: { lines: 60 } }` in `jest.config.ts`)

**Provider:** `v8`

**Roots scanned:** `<rootDir>/src`, `<rootDir>/tests`

## Accessibility Tests

Tests in `apps/web/tests/accessibility/` cover WCAG 2.1 AA compliance:
- Keyboard navigation: Tab order, Enter/Space activation, focus trap absence
- ARIA: All buttons have accessible names, `disabled` attribute (not just visual styling)
- Error states: Errors communicated via text, not color alone
- Focus management: Focus preserved across non-destructive re-renders
- Loading states: Text or disabled-state feedback beyond spinner
- Document structure: Headings, landmarks, semantic HTML

Pattern uses `@testing-library/user-event` for realistic keyboard simulation:
```typescript
import userEvent from "@testing-library/user-event";
const user = userEvent.setup();
await user.tab();
expect(document.activeElement).not.toBe(document.body);
```

## E2E Tests (Playwright)

**Framework:** Playwright 1.59+
**Config:** `apps/web/playwright.config.ts`
**Test dir:** `apps/web/tests/e2e/`
**Browser:** Chromium only (Desktop Chrome device preset)

**Settings:**
- Timeout: 60s per test, 10s for assertions
- Retries: 2 on CI, 0 locally
- Workers: 1 on CI (sequential), unlimited locally
- Traces: `on-first-retry`; Screenshots and video: `on-first-retry`
- Base URL: `http://localhost:3000` (dev server auto-started via `webServer` config)

**Note:** E2E tests are NOT run in the CI pipeline (`ci.yml`). They require a live dev server and full backend stack. Run locally only.

## CI Test Execution

The CI pipeline (`/.github/workflows/ci.yml`) runs:
1. `backend-lint` — ruff + pyright (no test execution)
2. `backend-test` — `uv run pytest tests/ -v --tb=short` with real PostgreSQL 17 and Redis 7 services
3. `frontend-lint` — eslint + tsc type-check (no test execution)
4. `frontend-build` — next build (no test execution)

**Frontend unit tests are not run in CI.** Jest must be run locally: `cd apps/web && npm test`.

## Test Fixtures (Images)

Physical test media files live at `tests/backend/` (top-level):
- `sample_evidence.png`, `test_image.webp` — generic evidence
- `invoice_ela_test.png` — ELA tool test
- `ai_persona_test.png`, `alley_object_test.png` — object detection
- `beach_gps_test.png` — GPS/metadata tests
- `whatsapp_context_test.png` — context analysis

---

*Testing analysis: 2026-04-16*
