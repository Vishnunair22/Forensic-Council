# Full Code Audit — Forensic Council

> **Purpose:** End-to-end runtime validation audit covering app stability, the full
> investigation flow (landing → upload → analysis → result), deep analysis, ML model
> integrity, API key wiring, security, and fail-safes.
>
> **Scope:** This is a runtime-validation audit, not a fresh build. Development is
> complete; this document is the checklist + surgical fix plan to harden the app.
>
> **How to read this:** Each section has **What to verify**, **Findings** (static-analysis
> results from the codebase), and **Action items**. Items tagged **[VERIFY]** require you
> to test in a running browser/backend because they cannot be confirmed by reading code.
> Items tagged **[FIX]** have a concrete code change in the Implementation Plan at the end.
> Items tagged **[DECISION]** need a product call before any code is written.

---

## 0. Audit Method & Limitations

This audit was produced by static analysis of the full codebase: routing, the three
core hooks (`useInvestigation`, `useResult`, `useSimulation`), the storage layer,
evidence/result components, the backend arbiter, the LLM/Gemini clients, the ML tool
registry, and config.

**What static analysis CANNOT confirm — you must verify these in a running app:**

- Visual cohesion, jerkiness, animation/transition smoothness, sound playback.
- Whether live LLM/Gemini keys authenticate, and whether quota/rate limits are hit.
- Actual ML model inference output quality at runtime.
- Real WebSocket reconnect races, refresh behavior, multi-tab behavior.

**Tooling to lean on instead of guessing:**

- `apps/api/scripts/verify_llm_keys.py --provider all --json` — checks Groq + Gemini
  key validity via `/models` endpoints, burns zero quota.
- `apps/api/scripts/validate_ml_tools.py` — validates all ML tool imports + binaries.
- `apps/api/scripts/verify_models_responding.py` — confirms models actually respond.
- `npm run test:a11y` (web) — Jest + Playwright axe accessibility sweep.
- `npm run test:e2e:journey` (web) — full-journey Playwright run.

---

## 1. App Refresh & Stability

### 1a. Clean refresh returns to the most stable component

**What to verify:** Refreshing mid-flow returns to a stable point, not a crash/404.

**Findings:**
- On `/evidence`, refresh during the loading overlay relies on `FC_SHOW_LOADING`
  (sessionStorage) + `loadPendingEvidenceFile()` (IndexedDB via
  `pendingFilePersistence.ts`).
- **Hard limitation:** a `File` object cannot survive a hard refresh — browsers do not
  allow restoring file handles. `useInvestigation` Effect A handles this with a toast
  ("File selection was lost after refresh") and routes safely.
- A 12s `OVERLAY_HARD_TIMEOUT_MS` safety net guarantees the overlay is never permanently
  stuck — good defense.
- Dev refresh always serves the latest code under `next dev`; no action needed for
  "loads latest code on refresh."

**Action items:**
- **[VERIFY]** Refresh mid-overlay → confirm toast + clean return, no stuck overlay/404.
- **[VERIFY]** Refresh during agent streaming on `/evidence` → confirm reconnect path
  (Effect B) re-attaches and agents resume, not a reset to empty state.

### 1b. Hard refresh returns to home hero (full app reset)

**Findings — SPEC CONTRADICTION:**
- A hard refresh on `/` correctly shows the hero.
- A hard refresh on `/result/{sid}` or `/evidence` **stays on that route**. It does NOT
  force back to hero. `useResult` re-runs, re-polls the arbiter, re-renders the report.
- This is arguably better UX (you don't lose the report) but it **contradicts the stated
  requirement** that a hard refresh act as a full reset.

**Action items:**
- **[DECISION]** Decide: (A) keep current behavior — refresh resumes the page (recommended,
  preserves work), and amend the spec; or (B) force hard-refresh-anywhere → hero, which
  requires an explicit mount/`pageshow` guard. Do not implement until decided.

### 1c. Global navbar as universal app reset

**Findings:**
- `GlobalNavbar.handleLogoClick` → `resetActiveInvestigation` (`appReset.ts`).
- On non-`/` routes it uses `window.location.href = "/"` (full document load = true
  reset). On `/` it uses `router.refresh()`. Consistent and correct.
- `resetActiveInvestigation` clears all `forensic_*` and `fc_*` keys, aborts the arbiter,
  clears the query cache, expires cookies, dispatches `fc:reset-home`.
- **Issue (medium) — investigator identity wiped:** `clearAllForensicKeys()` also removes
  `forensic_investigator_id`. History is explicitly preserved; investigator ID is not.
  After every reset a brand-new `REQ-XXXXXX` is minted.
- **Issue (low) — server-side logout is conditional:** `/api/v1/auth/logout` is only
  called when a `csrf_token` cookie is present. The `access_token` is httpOnly and can
  only be invalidated by the backend `Set-Cookie`. If `csrf_token` is missing but the
  `access_token` is still live, the session is not server-side invalidated — JS just
  forgets it.

**Action items:**
- **[DECISION]** Should investigator ID survive a reset (continuity) or be regenerated
  (clean identity each time)? If continuity → **[FIX 4]**.
- **[VERIFY]** Backend session/token lifetime. If sessions are long-lived, the conditional
  logout is a real gap; consider always attempting logout when any auth cookie exists.
- **[VERIFY]** Click the navbar logo from every route (`/`, `/evidence`, `/result/{sid}`,
  `/session-expired`, an error state) → confirm clean reset to hero each time.

---

## 2. App Load & Stability

### 2a/2b. Clean load, no jerkiness, no performance bottlenecks

**Findings:**
- Good: `HomeClient` lazy-loads `HowWorksSection`/`AgentsSection` via `next/dynamic` with
  min-height placeholders (prevents layout shift). `ResultLayout` lazy-loads
  `AgentAnalysisTab`/`HistoryPanel`.
- `buildKeyFindings` (`ResultLayout.tsx`) is heavy but `useMemo`'d — acceptable.
- **Concern — GPU cost:** `HomeClient` + `LandingBackground` render multiple
  `blur-[140px]`/`blur-[160px]` glow divs. Large blur radii are GPU-expensive and a
  common scroll-jank source on mid/low-end devices.
- `GlobalNavbar` scroll handler is `passive: true` and lightweight — fine.

**Action items:**
- **[VERIFY]** Scroll the landing page on a mid-range laptop and a phone; watch for jank.
  If janky, reduce blur radii or cap glow count.
- **[VERIFY]** Open DevTools Performance tab on first load of each route; confirm no long
  tasks > 50ms and no layout-shift spikes.

### 2c. Navigation connectivity (every button/route)

**Findings:**
- Every `router.push` target was traced and resolves to a real route. All error
  boundaries exist: `not-found.tsx`, `error.tsx`, `global-error.tsx`,
  `result/error.tsx`, `session-expired`.
- **Edge case:** `/result/page.tsx` with no sessionId redirects via cookie or
  `ResultClientRedirect`. A stale cookie routes to `/result/{stale-sid}` and `useResult`
  polling takes 30s+ to reach an error state.

**Action items:**
- **[VERIFY]** Walk every transition: Landing CTA → upload modal → success modal →
  `/evidence` → loading overlay → analysis page → HITL → arbiter overlay →
  `/result/{sid}` → New Analysis → upload modal; and `/result` → Back to Home → hero.
- **[VERIFY]** Visit `/result` directly with an expired session cookie; confirm the
  error state is reached without an excessive wait.

---

## 3. Landing Page

### 3a/3b/3c. Design cohesion, clean components, accessibility

**Findings:**
- Design system is consistent: `fc-surface`, `fc-btn-primary`, `fc-text-*`, all
  CSS-variable driven. No obvious stale/duplicate component code spotted in the landing
  path.
- Accessibility is genuinely strong: `aria-live` regions, `role="tab"`/`tablist`, focus
  traps (`useFocusTrap`), skip-link, `prefers-reduced-motion` respected throughout,
  `inert` on the hidden navbar, decorative glows `aria-hidden`.

**Action items:**
- **[VERIFY]** Run `npm run test:a11y` — treat the axe suite output as the authoritative
  a11y sweep for the landing page (more reliable than manual inspection).
- **[VERIFY]** Visual cohesion pass navbar → hero → How-It-Works → Agents → footer:
  gradients, shadows, spacing, hover states.
- **[VERIFY]** Tab through the entire landing page with the keyboard only; confirm focus
  order and visible focus rings.

---

## 4. Landing CTA → Upload Modal → File Selection → Upload Success Modal

### 4a/4b. Trace the flow (UI + backend + connectivity)

**Findings:**
- Flow: `HeroAuthActions` CTA → `UploadModal` → file picker → `setSelectedFile` →
  `UploadSuccessModal` → `handleStartAnalysis` writes `__pendingFileStore.file`, sets
  `AUTO_START`/`FC_SHOW_LOADING`, navigates to `/evidence`.
- `handleCTAClick` pre-authenticates in parallel (`autoLoginAsInvestigator`) and stores
  the promise — `/evidence` awaits it. Good latency hiding.
- Body scroll-lock is managed in one effect keyed on `showUpload` — no mount/unmount race.
- `closeUpload` refocuses the CTA via `requestAnimationFrame` — correct a11y.

**Action items:**
- **[VERIFY]** Upload each supported file type; confirm `fileValidation.ts` accepts valid
  and rejects invalid (empty, oversized, unsupported MIME, corrupt).
- **[VERIFY]** Backend `startInvestigation` returns a session ID; duplicate upload returns
  409 → `DuplicateInvestigationError` → reconnect (not error).

### 4c. Design audit — upload modal & success modal

**Action items:**
- **[VERIFY]** Visual + interaction audit of `UploadModal` and `UploadSuccessModal`:
  drag-drop state, file chip, transitions between the two modals (`AnimatePresence
  mode="wait"`).

### 4d. Animations, transitions, sounds

**Findings:**
- Sounds wired: `envelope-open` (CTA), `scan` (start analysis). `useSound` wraps all
  playback in try/catch so a failed sound never blocks the flow.

**Action items:**
- **[VERIFY]** Hear each sound fire; watch modal transitions for jank.

---

## 5. Upload Success → Loading Overlay → Evidence Analysis Page

### 5a/5b/5c/5d. Flow, overlay design, live broadcast, animations

**Findings:**
- `useInvestigation` syncs `uploadPhaseText`/`pipelineMessage` → `FC_LOADING_TEXT` and a
  dispatched-agent count → sessionStorage; `GlobalLoadingOverlay` reads them. The live
  broadcast is real pipeline text.
- Overlay dismissal: as soon as the WS handshake completes or the pipeline emits a
  non-idle status, with a 1s minimum for perceived smoothness and a 12s hard timeout.

**Action items:**
- **[VERIFY]** Loading overlay shows live, changing text — not stuck on "Initializing
  workspace."
- **[VERIFY]** Overlay design audit; confirm overlay dismisses cleanly into the analysis
  page with no flash/jank.

---

## 6. Evidence Analysis Page & `AgentProgressDisplay.tsx`

### 6.a1–a3. Page load → live progress → agent cards with findings

**Findings:**
- `AgentProgressDisplay` (569 lines) renders per-agent cards with verdict, confidence
  score, agent brief, tool strip, tool findings, and a "More Findings" expandable
  section.
- a11y present: `aria-expanded`/`aria-controls` on expandables, `aria-live="polite"` on
  the live status region.

**Action items:**
- **[VERIFY]** Full lifecycle: page load → agents start → live progress text streams →
  initial analysis finishes → every card shows verdict, confidence, brief, tool strip,
  tool findings.
- **[VERIFY]** "More Findings" expands and collapses cleanly with no layout jump.
- **[VERIFY]** Contrast + font size of all findings text — no visibility issues
  (cross-check with the a11y suite).

### 6.4. HITL checkpoint → decision buttons

**Findings:**
- `HITLCheckpointModal` renders on `hitlCheckpoint`; decisions submit via
  `submitHITLDecision`. Double-submit guarded by `isSubmittingHITL`.

### 6.4.1–4.5. Accept Analysis → Arbiter overlay → Initial result page

**Findings:**
- `handleAcceptAnalysis`: guarded by `isNavigating` + `resumeInFlightRef` (double-click
  safe), plays `arbiter_start`, calls `resumeInvestigation(false)`, polls
  `waitForFinalReport` (up to 600s), then routes to `/result/{sid}`.
- Arbiter overlay = `ArbiterDeliberationOverlay`; live text piped from `arbiterThinking`.
- **Groq usage:** the arbiter uses Groq (`llama-3.3-70b-versatile`) for **narrative
  synthesis only**. The verdict is computed **deterministically** from structured
  findings (confirmed in `arbiter.py` / README). This is the correct court-grade design —
  the LLM never assigns the verdict.

**Action items:**
- **[VERIFY]** Accept Analysis → arbiter overlay appears with live progress text → initial
  result page loads with no error.
- **[VERIFY]** Double-click "Accept Analysis" → only one resume fires.

### 5. Result page structure, accuracy, court-grade quality

**Findings:**
- `buildKeyFindings` has solid anti-degradation logic: `isLowValueFinding` filters
  templates, "no significant findings," tool-echo negatives, lorem ipsum; dedup via a
  normalized key set; tiered synthesis (statistical → LLM key_findings → tool findings).
  This directly addresses the "no duplicate/degraded/template findings" requirement.
- `DegradationBanner` surfaces `degradation_flags` (e.g. "LLM synthesis bypassed") — this
  is the live signal that Groq was unavailable/rate-limited.

**Action items (5.1):**
- **[VERIFY]** Read every field on a real initial result page: verdict, confidence,
  manipulation probability, error rate, discord, intelligence brief, agent strip, agent
  findings, metrics, timeline, integrity. Confirm no duplicate/degraded/template text.

**Action items (5.2 — court-admissibility suggestions):**
- Consider adding, if not already present: an explicit **chain-of-custody section** on
  the result page (the backend has `custody_chain.py` + `CHAIN_OF_CUSTODY.md` — surface
  the ledger), a **methodology/limitations statement**, **examiner/tool version
  provenance**, and a **cryptographic signature panel** (`ReportIntegrity` exists —
  confirm it shows the signature + hash prominently).
- **[VERIFY]** Whether `ReportIntegrity` already covers signature/hash; if so, no new
  section needed — just confirm prominence.

**Action items (5.3 — API key usage; see also Section 11):**
- See the dedicated **Section 11 — API Key & Quota Audit** below.

**Action items (5.4):**
- **[VERIFY]** Findings are real model output, not deterministic placeholder text. If
  `degradation_flags` shows "LLM synthesis bypassed" on a normal run, the Groq key is
  missing/rate-limited — fix the key, not the UI.

**Action items (5.5 — History panel):**
- **Findings:** select / select-all / delete-selected / clear-all / row-navigate are all
  wired via `useSessionStorage`. History capped at 50 (`HISTORY_MAX`).
- **Issue (low):** `useSessionStorage` actually uses `localStorage` (persistent), not
  `sessionStorage` — the name is misleading. Correct behavior, wrong name → **[FIX 6]**.
- **[VERIFY]** Each history action works; selecting a past investigation loads its report.

**Action items (5.6 — Export):**
- **CRITICAL — DOCX export does not exist.** Backend (`sessions.py:570`) has only
  `/report/pdf` (with HTML and JSON fallback). The frontend `ExportDropdown` offers only
  **PDF and JSON**. There is no DOCX path anywhere. → **[DECISION]** + **[FIX 3]**.
- **Issue (medium) — silent PDF→JSON fallback:** `ExportDropdown.handlePdf` silently
  calls `onExportJson()` on PDF failure — the user asked for PDF, gets a JSON file, no
  explanation. `ActionDock` does this correctly with a toast. → **[FIX 1]**.
- **Issue (low) — dead code:** `ActionDock.tsx` has a full export implementation but
  `ResultLayout` uses `PageNavigation` instead and never renders `ActionDock`. Likely
  dead code → **[FIX 2]**.
- **[VERIFY]** PDF export downloads a valid PDF; JSON export downloads valid JSON.

### 6.a (result page navigation)

**Findings:**
- New Analysis → `_resetAndNavigate("/?upload=1")` → upload modal reopens.
- Back to Home → `_resetAndNavigate("/#hero")` → hero. Both preserve history correctly.

**Action items:**
- **[VERIFY]** Both navigation buttons reset cleanly and land on the right place.

---

## 7. Deep Analysis Flow

### 7.1–7.3. Clean start, no handover, own tool set, live progress

**Findings:**
- `handleDeepAnalysis`: sets `IS_DEEP`, clears completed agents, removes stale
  `DEEP_AGENTS:{sid}`, sets phase `deep`. **Deliberately does NOT reconnect the
  WebSocket** — a comment explains that closing/reopening creates a race where deep-phase
  messages sent right after `/resume` are lost.
- `loadAgentTimelineForSession` returns ONLY deep agents when `isDeep` — never falls back
  to initial findings. Deep and initial are correctly isolated.
- Deep tool set is separate: `task_tool_config.py` defines `gemini_deep_forensic`,
  `voice_clone_deep_ensemble`, `anti_spoofing_deep_ensemble`, `deepfake_frequency_check`.
  Tool routing per file type is in `task_router.py`.

**Action items:**
- **[VERIFY]** Click Deep Analysis after initial → deep analysis starts cleanly, live
  progress text begins, no initial-phase findings leak into the deep cards.
- **[VERIFY]** For each file type, the correct deep tools fire and unsupported tools are
  skipped (e.g. image file → image/metadata deep tools, audio/video tools skipped).

### 7.4–7.8. Per-agent findings, completion, HITL, View Results, deep result page

**Findings:**
- `handleViewResults` mirrors `handleAcceptAnalysis`: guarded, polls
  `waitForFinalReport`, routes to `/result/{sid}`. The deep result page reads
  `DEEP_AGENTS:{sid}` and `RESULT_PHASE=deep`.
- `DeepModelTelemetry` renders only when `cross_modal_fusion` actually ran.

**Action items:**
- **[VERIFY]** Deep analysis finishes → HITL checkpoint → View Results → arbiter overlay →
  deep result page. Confirm per-agent findings are design- and content-solid.
- **[VERIFY]** Deep result page: history panel, export, navigation all intact.
- **[VERIFY]** Deep result page is visually distinct/correct vs initial (deep telemetry
  section, `is_deep_analysis` flag honored).

---

## 8. ML Model Integrity & Leverage (APPENDED)

> **Architecture clarification — important.** The app is **not fully local**. It runs on
> **two tiers**: (1) **local ML models** — HuggingFace/torch models executed in
> subprocesses (`ml_subprocess.py`, `ml_tool_worker.py`); and (2) **remote LLM APIs** —
> Groq (synthesis/reasoning) and Gemini (vision/audio deep analysis). The statement "I
> only have ML models that are fully local" is **not accurate for this codebase** —
> Groq and Gemini are remote API dependencies. See Section 11 for how to handle this.

### 8a. Local ML model inventory (from `config/models.lock.json`)

Local models the app is built to leverage:

- `Vansh180/deepfake-audio-wav2vec2` — primary audio deepfake detection (**required**).
- `clovaai/AASIST` — audio anti-spoofing fallback (research-only license, opt-in).
- `pyannote/speaker-diarization-3.1` — speaker diarization (needs `HF_TOKEN`).
- `openai/clip-vit-base-patch32` — default CLIP / OpenCLIP ViT-B/32 (**required**).
- `openai/clip-vit-large-patch14`, `laion/CLIP-ViT-H-14-...` — higher-precision CLIP
  (opt-in).
- `microsoft/swinv2-tiny-...`, `facebook/detr-resnet-50` — image classifier / object
  detection (Apache-2.0 alternatives to YOLO).
- `resnet50_torchvision` — ResNet-50 weights (**required**).
- `openai/whisper-base` — audio transcription verification (opt-in).
- `microsoft/table-transformer-detection` — PDF/document structure (opt-in).
- Plus toolchain binaries: `exiftool`, `ffmpeg`, `tesseract`; libs: `opencv`, `easyocr`,
  `open_clip`, `speechbrain`, `ultralytics`, `torch/torchaudio/torchvision`.

### 8b. What to verify — models return valid findings

**Action items:**
- **[VERIFY]** Run `apps/api/scripts/validate_ml_tools.py` — confirms every ML import and
  binary is present in the runtime image.
- **[VERIFY]** Run `apps/api/scripts/verify_models_responding.py` — confirms each model
  actually loads and produces output.
- **[VERIFY]** Run `apps/api/scripts/model_cache_check.py` / `model_pre_download.py` —
  confirm all **required** models are cached so the first investigation isn't a cold
  download.
- **[VERIFY]** For each agent (1 image, 2 audio, 3 scene, 4 video, 5 metadata), run a real
  file of that type and confirm tool findings are **non-empty, plausible, and not
  echo-negatives** ("found no anomalies" with nothing else). Tool-echo negatives are
  filtered from the result page by `isLowValueFinding`, but the agent card should still
  show genuine analysis.
- **[VERIFY]** Confirm every model in `models.lock.json` marked `required: true` is
  actually exercised by at least one tool. If a required model is never called, either
  it's mis-flagged or a tool is missing.
- **[VERIFY]** Opt-in models (Whisper, AASIST, table-transformer, large CLIP): decide
  per-model whether to enable. If enabled, confirm the env var that activates them is set
  and the model is cached. If not enabled, they should not appear in any tool path.

### 8c. ML model leverage — surgical checks

**Action items:**
- **[VERIFY]** `task_tool_config.py` + `task_router.py`: every local model maps to a tool,
  and every tool maps to an agent + file type. No orphaned models, no tool referencing a
  model that isn't downloaded.
- **[VERIFY]** Deep-analysis tools (`*_deep_*`) use the local ensemble models, not just
  re-running initial tools. Confirm `voice_clone_deep_ensemble` and
  `anti_spoofing_deep_ensemble` actually load distinct models.
- **[VERIFY]** Subprocess isolation: `ml_subprocess.py` warmup/worker mode loads models
  once; confirm models are not reloaded per-call (a major latency bottleneck if so).
- **[FIX — investigate]** If any required model has `revision: "main"` and `sha256: null`
  with `_enforce_sha: false`, production builds pull an unpinned revision. For court-grade
  reproducibility, pin each required model to a specific Git SHA and set `sha256`. This is
  a provenance/reproducibility hardening item, not a runtime blocker.

---

## 9. API Key Usage Audit (APPENDED)

### 9a. Key inventory (from `core/config.py`)

- `LLM_API_KEY` — Groq key for agent + arbiter synthesis (`gsk_...`).
- `ARBITER_LLM_API_KEY` — optional dedicated arbiter key; falls back to `LLM_API_KEY`.
- `GEMINI_API_KEY` — Gemini key for Agents 1/3/5 vision/audio deep analysis (`AIza...`).
- `ARBITER_GEMINI_API_KEY` — optional dedicated arbiter Gemini key; empty = share main.
- `QDRANT_API_KEY` — vector DB key (RAG knowledge store).
- `HF_TOKEN` — HuggingFace token, needed for gated models (pyannote).

### 9b. Findings — wiring

- Keys are validated at config load: `validate_llm_api_key` (required when
  `LLM_PROVIDER` is set, length-checked), `validate_gemini_api_key` (warns if missing or
  < 20 chars), `gemini_api_key_policy_ok` gate.
- `core/llm_client.py` builds per-`provider:model` circuit breakers and supports a
  cross-provider fallback cascade (`gemini/model` specs). Arbiter vs agent keys/models
  are resolved separately.
- `core/gemini_client.py` has a fallback model cascade
  (`gemini-2.5-flash → flash-lite → 2.0-flash → 2.0-flash-lite`) and a
  `_local_forensic_fallback` when Gemini is unavailable/disabled.
- README documents the no-key fallback: no Groq key → agents use local tool-only
  analysis; arbiter produces a deterministic report with `confidence=0.55`.

**This wiring is sound.** The keys are correctly separated, validated, circuit-broken,
and have graceful local fallbacks.

### 9c. Action items

- **[VERIFY]** Run `apps/api/scripts/verify_llm_keys.py --provider all --json` — confirms
  both keys authenticate, zero quota burned.
- **[VERIFY]** Confirm `.env` has `LLM_API_KEY` and `GEMINI_API_KEY` set with valid keys
  (and `HF_TOKEN` if pyannote diarization is used).
- **[VERIFY]** Decide whether to use dedicated arbiter keys (`ARBITER_LLM_API_KEY`,
  `ARBITER_GEMINI_API_KEY`). Using a separate key for the arbiter isolates its quota from
  agent calls and reduces rate-limit collisions — recommended if you have a second key.
- **[VERIFY]** On a real run, check the result page `degradation_flags`. "LLM synthesis
  bypassed" means the Groq key failed or was rate-limited at runtime — that is the live
  symptom of a key/quota problem.
- **[VERIFY]** Confirm no API key is ever sent to or exposed in the frontend. The web app
  only talks to its own `/api/v1/*` proxy; keys live server-side only. Spot-check that no
  key string appears in any `apps/web` file or network response.

---

## 10. Quota Strategy — Smart Wiring, Remove the Quota Meter (APPENDED)

> **Your instruction:** keep API quota from being reached via *smart wiring*, and
> **remove the per-session quota meter** because you don't need a UI meter.

**Two separate things — do not conflate them:**

1. **`core/quota_meter.py` + `QuotaResponseDTO` + `GET /{session_id}/quota` endpoint** —
   this is the **per-session metering/reporting** feature (tracks API call counts in
   Redis, exposes them on an SSE "metrics" event and a REST endpoint). This is the
   "quota meter" you want removed. **It is safe to remove** — it is reporting only.

2. **`core/provider_quota_guard.py` (`ProviderQuotaGuard`)** — this is **pre-call rate-limit
   enforcement** (per-minute/per-day sliding window; returns False so callers degrade
   gracefully instead of getting 429s). **This IS the "smart wiring" that prevents quota
   from being reached. DO NOT remove it.** Removing it would cause exactly the rate-limit
   429s you want to avoid.

**Recommendation:** Remove tier (1), keep tier (2). The combination of `ProviderQuotaGuard`
+ per-`provider:model` circuit breakers + the Gemini fallback cascade + local fallbacks
IS the smart-wiring quota strategy. → **[FIX 5]**.

**Action items:**
- **[FIX 5]** Remove the quota-meter reporting feature (`quota_meter.py`, the `/quota`
  endpoint, `QuotaResponseDTO`, the SSE "metrics" quota payload) — see Implementation Plan.
- **[KEEP]** `ProviderQuotaGuard`, circuit breakers, fallback cascades — these are the
  smart wiring; leave them fully intact.
- **[VERIFY]** After removal, confirm `provider_quota_guard.py` still configures correctly
  at startup (`api/main.py` line ~315) and no removed import breaks the boot path.

---

## 11. Security, Error Handling & Fail-safes

**Findings:**
- **CSP (`middleware.ts`)** includes `'unsafe-inline'` for `script-src` in **all**
  environments and `'unsafe-eval'` in dev. `'unsafe-inline'` script-src in production
  meaningfully weakens XSS protection — notable for a court-grade tool. → **[FIX 5b]**.
- **401 handling:** `apiFetch` intercepts 401 → expires cookies →
  `/?session_expired=true`. Consistent and correct.
- **Schema fallback:** `_parseReportDTO` passes raw data through on Zod failure rather
  than crashing — pragmatic; logs telemetry.
- **Error boundaries:** all present (`error.tsx`, `global-error.tsx`, route-level).
- **Rate-limit defense:** circuit breakers + `ProviderQuotaGuard` + fallback cascades
  exist (see Section 10).

**Action items:**
- **[FIX 5b]** Harden production CSP — move to a nonce-based `script-src`, drop
  `'unsafe-inline'`. Larger change; scope as its own task.
- **[VERIFY]** Kill the network during upload, during WS streaming, and during arbiter
  polling — confirm `ForensicErrorModal` + retry recovers each.
- **[VERIFY]** Let the auth token expire mid-analysis — confirm graceful session-expired
  redirect, no infinite loop.
- **[VERIFY]** Upload empty / unsupported / corrupt / oversized files — confirm each
  rejection path.

---

## 12. Gaps in the Original Plan — Additional Test Areas

These were not in the original plan and must be added:

1. **Concurrency / double-submit** — rapid double-clicks on "Begin Analysis", "Accept
   Analysis", "Deep Analysis", "View Results". Guards exist (`investigationInFlightRef`,
   `resumeInFlightRef`, `isNavigating`, `isSubmittingHITL`) — test them.
2. **Browser back/forward + bfcache** — `EvidenceUploadClient` has a `pageshow` handler;
   test start → Back → Forward.
3. **Multi-tab** — `localStorage` is shared; `storage` events fire cross-tab. Run an
   analysis in one tab; confirm the other does not corrupt state.
4. **Network failure mid-flow** — covered in Section 11; explicitly enumerate each stage.
5. **Session expiry mid-analysis** — token expires while agents run.
6. **File-validation matrix** — empty, oversized, unsupported MIME, corrupt, zero-byte.
7. **Mobile / responsive / touch** — fixed nav + bottom action bar + `env(safe-area-inset)`
   on real devices.
8. **Investigator-ID lifecycle** — decided in 1c.
9. **DOCX export** — decided in 5.6.
10. **Hard-refresh-as-reset contradiction** — decided in 1b.
11. **`ActionDock` dead-code** — confirm + remove.
12. **Accessibility regression** — run `npm run test:a11y` as a formal plan step.
13. **ML model cold-start** — first investigation after a fresh deploy (model download
    latency) vs warm.
14. **Required-model pinning** — `models.lock.json` SHA pinning for reproducibility.

---

## 13. Implementation Plan — Surgical Fixes

Ordered by severity. Nothing here is executed until you approve and resolve the
**[DECISION]** items.

### FIX 1 — Silent PDF→JSON fallback (medium)

**File:** `apps/web/src/components/result/ResultLayout.tsx` (`ExportDropdown.handlePdf`)

Add a toast so the user knows they received JSON instead of PDF:

```tsx
import { toast } from "@/hooks/use-toast";

// inside handlePdf — replace the bare `catch {}` / silent fall-through:
} catch {
  toast.warning({
    title: "PDF export unavailable",
    description: "Downloading the report as JSON instead.",
  });
} finally {
  setExporting(false);
}
onExportJson();
```

### FIX 2 — Dead code: `ActionDock` (low)

```bash
grep -rn "ActionDock" apps/web/src
```

If only `ActionDock.tsx` and its own test reference it, delete
`apps/web/src/components/result/ActionDock.tsx` and the test. If something imports it,
consolidate to a single export component (`ExportDropdown`). Goal: one export
implementation, not two divergent ones.

### FIX 3 — DOCX export (medium) — **[DECISION REQUIRED]**

**If DOCX is wanted:**
- New backend file `apps/api/core/docx_report_exporter.py` using `python-docx`, mirroring
  `core/pdf_report_exporter.py`'s structure.
- New route in `apps/api/api/routes/sessions.py` near line 570:
  `GET /{session_id}/report/docx` → returns the `.docx` blob.
- Add a third item to `ExportDropdown` in `ResultLayout.tsx` (`FileText` icon, "DOCX
  Report"), calling the new endpoint with the same blob-download pattern as `handlePdf`.

**If DOCX is not wanted:** remove "docx" from the audit spec — no code change.

### FIX 4 — Investigator ID survives reset (medium) — **[DECISION REQUIRED]**

**File:** `apps/web/src/lib/appReset.ts` (only if continuity is desired)

```ts
// before clearAllForensicKeys:
const savedInvestigatorId = storage.getItem(STORAGE_KEYS.INVESTIGATOR_ID);

storage.clearAllForensicKeys();
sessionOnlyStorage.clearAllForensicKeys();

if (savedHistory.length > 0) {
  storage.setItem(STORAGE_KEYS.HISTORY, savedHistory, true);
}
if (savedInvestigatorId) {
  storage.setItem(STORAGE_KEYS.INVESTIGATOR_ID, savedInvestigatorId);
}
```

### FIX 5 — Remove the per-session quota meter (keep the quota guard)

**Remove (reporting feature):**
- `apps/api/core/quota_meter.py` — delete the file.
- `apps/api/api/routes/sessions.py` — delete the `GET /{session_id}/quota` endpoint
  (around line 1011) and its `QuotaResponseDTO` import.
- `apps/api/api/schemas.py` — remove `QuotaResponseDTO` if unused elsewhere.
- Remove the quota payload from the SSE "metrics" event emitter.
- `core/llm_client.py` / `core/gemini_client.py` — remove `quota_meter` imports and the
  `session_id_ctx` recording calls (keep the LLM call logic itself).
- `api/main.py` — remove any `quota_meter` import.

**Keep (smart wiring — do NOT touch):**
- `apps/api/core/provider_quota_guard.py` (`ProviderQuotaGuard`).
- Per-`provider:model` circuit breakers in `llm_client.py`.
- Gemini fallback cascade, local fallbacks.

**After removal:** run the API test suite and confirm `api/main.py` still boots and
`ProviderQuotaGuard` still configures (line ~315).

### FIX 5b — Production CSP hardening (security, larger task)

**File:** `apps/web/src/middleware.ts`

Move production `script-src` to a nonce-based policy; drop `'unsafe-inline'`. Requires
generating a per-request nonce and threading it to inline `<script>` tags. Scope as its
own task — do not bundle with the smaller fixes.

### FIX 6 — Rename `useSessionStorage` → `usePersistentStorage` (low)

The hook uses `localStorage`, not `sessionStorage`. Mechanical rename across
`apps/web/src/hooks/useSessionStorage.ts` and its consumer
`apps/web/src/components/result/HistoryPanel.tsx`. Prevents future confusion; no behavior
change.

---

## 14. Decisions Required Before Implementation

1. **Hard-refresh behavior (1b)** — resume the page (recommended) or force reset to hero?
2. **Investigator ID on reset (1c / FIX 4)** — preserve for continuity or regenerate?
3. **DOCX export (5.6 / FIX 3)** — build it, or drop it from the spec?
4. **Dedicated arbiter API keys (9c)** — use `ARBITER_LLM_API_KEY` /
   `ARBITER_GEMINI_API_KEY` for quota isolation?
5. **Quota meter removal (FIX 5)** — confirm you want the *reporting* feature removed and
   the *guard* kept (recommended split).

---

## 15. Execution Order (once approved)

1. Run all verification scripts (`verify_llm_keys`, `validate_ml_tools`,
   `verify_models_responding`, `model_cache_check`) and `npm run test:a11y` /
   `test:e2e:journey` — establish a baseline.
2. Apply low-risk fixes: FIX 1, FIX 2, FIX 6.
3. Apply FIX 5 (quota meter removal) — then re-run the API test suite.
4. Apply FIX 3 and FIX 4 if their decisions are "yes".
5. Schedule FIX 5b (CSP) as a standalone hardening task.
6. Work through every **[VERIFY]** item in a running app, section by section.
7. Re-run the full test + a11y + e2e suites as a final gate.
