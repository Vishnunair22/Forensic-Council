# Forensic Council — Applied Audit Changes (v3 → v4)

See `FORENSIC_AUDIT_PLAN.md` (in audit outputs) for the full forensic report.

## Changes Applied

### DOCKER-001 — Critical: Fatal Migration Failures
- **File:** `apps/api/Dockerfile` line 134
- **Change:** Removed `2>/dev/null || true` silencing from alembic migration CMD
- **Impact:** Failed migrations now crash startup instead of silently continuing with a broken schema

### FE-HITL-001 — Critical: useState Hook Misuse
- **File:** `apps/web/src/components/evidence/HITLCheckpointModal.tsx` lines 59–68
- **Change:** Replaced illegal `useState()` side-effect initializer with `useEffect()`
- **Impact:** Eliminated memory leak, stale state updates on unmounted component, React StrictMode bugs

### DOCKER-003 — High: Committed Credentials
- **File:** `scratch/fc_cookies.txt`, `scratch/smoke.png`, `scratch/test_evidence.png`
- **Change:** Removed committed JWT token, CSRF token, and test images from repository
- **Impact:** Eliminated credential exposure risk; updated `.gitignore` to prevent recurrence
- **Action Required:** Rotate JWT_SECRET_KEY if `scratch/fc_cookies.txt` was ever exposed externally

### DOCKER-004 — Medium: CSP Conflict (Caddy vs Next.js)
- **File:** `infra/Caddyfile` lines 25–27
- **Change:** Removed conflicting `Content-Security-Policy` header from Caddy
- **Impact:** Next.js middleware is now the sole CSP authority; eliminates silent breakage of `'unsafe-inline'` in production

### FE-A11Y-001 — High: Reduced Motion Not Respected
- **Files:** `ForensicProgressOverlay.tsx`, `LoadingOverlay.tsx`, `UploadModal.tsx`
- **Change:** Added `useReducedMotion()` hook; all framer-motion animations respect `prefers-reduced-motion`
- **Impact:** WCAG 2.1 AA criterion 2.3.3 now satisfied; eliminates vestibular disorder risk

### FE-A11Y-002 — High: Missing Live Region on Result Page
- **File:** `apps/web/src/components/result/ResultStateView.tsx`
- **Change:** Added `role="status" aria-live="polite"` region for state transition announcements
- **Impact:** Screen reader users now hear when report is ready or an error occurs

### FE-HITL-002 — High: Radio Group Keyboard Navigation
- **File:** `apps/web/src/components/evidence/HITLCheckpointModal.tsx`
- **Change:** Added `onKeyDown` arrow-key navigation, `tabIndex` roving focus, `type="button"`, `aria-labelledby`
- **Impact:** HITL decision grid is now keyboard-navigable per ARIA radiogroup pattern

### UX-UPLOAD-001 — Medium: No Submit Feedback in Upload Modal
- **File:** `apps/web/src/components/evidence/UploadModal.tsx`
- **Change:** Added `role="status" aria-live="polite"` submitting indicator; UPLOADING status in corner badge
- **Impact:** Users with slow connections see immediate feedback after file selection

### BE-ML-001 — Medium: Unbounded ML Subprocess Execution
- **Files:** `apps/api/core/ml_subprocess.py`, `apps/api/core/config.py`, `.env.example`
- **Change:** Added `ml_subprocess_timeout_s` setting (default 120s); enforced as ceiling on all subprocess calls
- **Impact:** Hung/OOM ML subprocesses now time out within 120s instead of blocking indefinitely

### CFG-001 — Medium: Misleading .env.example Documentation
- **File:** `.env.example`
- **Change:** Clarified that `COMPOSE_PROJECT_NAME` is overridden by `name:` in docker-compose.yml; improved ACME_EMAIL warning

### POLISH-001 — Low: CI Artifact Committed
- **File:** `.gitignore`
- **Change:** Added `ruff_errors.json` and `*.ruff_errors.json` to `.gitignore`

### POLISH-002 — Low: A11y Tests Never Run in CI
- **Files:** `.github/workflows/ci.yml`, `apps/web/package.json`
- **Change:** Added `test:a11y` npm script; added `frontend-a11y` CI job that runs axe-playwright against the built app


---

# Forensic Council — Applied Audit Changes (v4 → v5)

## Phase 1: Backend Lint — Zero Ruff Errors

### BE-LINT-001 — Medium: Unused Imports (12 instances)
- **Files:** `api/routes/cases.py`, `api/routes/webhooks.py`, `core/pdf_report_exporter.py`, `alembic/versions/0001_initial_schema.py`
- **Change:** Removed 12 unused imports (`json`, `os`, `time`, `JSONResponse`, `UUID`, `get_settings`, `io`, `Union`, `sqlalchemy`)

### BE-SEC-001/002 — Medium: Insecure `hashlib.md5` (3 instances)
- **Files:** `core/rag_forensic_knowledge.py`, `core/task_router.py`
- **Change:** Added `usedforsecurity=False` to all non-cryptographic `md5()` calls (n-gram vectorization and tool-set fingerprinting); silences FIPS-mode false alarms

### BE-SEC-003–007 — Low: Silent `except: pass` (8 instances)
- **Files:** `agents/arbiter_narrative.py`, `api/routes/auth.py`, `api/routes/investigation.py`, `api/routes/webhooks.py` (×2), `core/ml_subprocess.py`, `tools/ocr_tools.py`, `api/routes/sessions.py`
- **Change:** All 8 bare `except: pass` / `except: continue` blocks replaced with `logger.debug(...)` with `error=str(exc)` context; S110/S112 ruff rules now pass

### BE-NAMING-001 — Low: Platt Scaling Variable Names (N806 violations)
- **File:** `core/calibration_trainer.py`
- **Change:** Renamed `A`→`platt_a`, `B`→`platt_b`, `d_A`→`grad_a`, `d_B`→`grad_b` throughout function bodies, signatures, `CalibrationTrainingResult` dataclass fields, all call sites, and logger kwargs. Eliminates 8 N806 naming violations

### BE-NAMING-002 — Low: `AGENT_TIMEOUT` in function scope (N806)
- **File:** `orchestration/pipeline_phases.py`
- **Change:** Renamed `AGENT_TIMEOUT = 300` → `agent_timeout = 300`

### BE-COMPAT-001 — Low: `zip()` without `strict=` (5 instances, B905)
- **Files:** `core/calibration_trainer.py`, `core/rag_forensic_knowledge.py`, `core/task_router.py`
- **Change:** Added `strict=True` to training-loop `zip()` calls (equal-length invariant must hold) and `strict=False` to cosine similarity (vectors may legally differ by design)

### BE-MISC — Low: Additional fixable ruff issues
- `N811`: `WeasyHTML` → `WEASY_HTML` in `core/pdf_report_exporter.py`
- `F841`: Removed unused `except Exception as e` in `agents/agent1_image.py`
- `UP007`: Modernized `Union[X, None]` → `X | None` in `alembic/`
- `S311`: Added `# noqa: S311` with justification to synthetic data `random` usage
- `W291`: Removed trailing whitespace in migration file

## Phase 2: Frontend Motion & Accessibility

### FE-MOTION-001 — High: Landing page hero animations unguarded (WCAG 2.3.3)
- **File:** `apps/web/src/app/page.tsx`
- **Change:** Added `useReducedMotion()` hook; `variants`, `initial`, and `animate` props disabled when motion is reduced

### FE-MOTION-002 — High: CTA button `whileHover`/`whileTap` unguarded
- **File:** `apps/web/src/components/ui/HeroAuthActions.tsx`
- **Change:** Added `useReducedMotion()`; `whileHover` and `whileTap` set to `undefined` when motion is reduced

### FE-MOTION-003 — Medium: Evidence page empty-state animation unguarded
- **File:** `apps/web/src/app/evidence/page.tsx`
- **Change:** Added `useReducedMotion()`; `initial` prop disabled when motion is reduced

### FE-A11Y-003 — High: GlobalNavbar `aria-hidden` misuse
- **File:** `apps/web/src/components/ui/GlobalNavbar.tsx`
- **Change:** Replaced `aria-hidden={!isVisible}` (incorrect — permanently removes nav from AT, including when visible) with the HTML `inert=""` attribute, which is the correct mechanism for off-screen interactive content; adds `inert?: "" | undefined` declaration to `global.d.ts` for React 18 TypeScript compatibility

### FE-STYLE-002 — Low: Duplicate comment in HITLCheckpointModal
- **File:** `apps/web/src/components/evidence/HITLCheckpointModal.tsx`
- **Change:** Removed duplicate "Small delay before rendering content" comment

## Phase 3: Memory Leaks & Infrastructure

### FE-LEAK-001 — Medium: `minOverlayTimerRef` not cleared on unmount
- **File:** `apps/web/src/hooks/useInvestigation.ts`
- **Change:** Added `clearTimeout(minOverlayTimerRef.current)` to the unmount cleanup `useEffect`; prevents state update on unmounted component

### FE-LEAK-002 — Medium: Reconnect `setTimeout` untracked — fires after unmount
- **File:** `apps/web/src/hooks/useSimulation.ts`
- **Change:** Added `reconnectTimerRef` to track the reconnect delay timer; it is cancelled in the unmount-only `useEffect` cleanup; prevents ghost reconnection attempts after component dismounts

### SEC-001 — Medium: Missing `Cross-Origin-Opener-Policy` and `Cross-Origin-Embedder-Policy`
- **File:** `infra/Caddyfile`
- **Change:** Added `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp`; required for process isolation and `SharedArrayBuffer` (used by audio/video WASM tools); also added `Permissions-Policy` for feature restriction

### PERF-001 — Low: No immutable cache headers for Next.js static assets
- **File:** `infra/Caddyfile`
- **Change:** Added `handle /_next/static/*` block with `Cache-Control: public, max-age=31536000, immutable`; Next.js generates content-hashed filenames so these assets can be cached forever, eliminating redundant network requests on revisits

### REPO-001 — Low: `scratch/*.py` not gitignored
- **File:** `.gitignore`
- **Change:** Added `scratch/*.py` to prevent accidental commit of utility scripts like `scratch/check_health.py`
