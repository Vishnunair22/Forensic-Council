# Forensic Council — Frontend Surgical Audit & Implementation Plan

> **Scope:** All files under `apps/web/src/` plus `next.config.ts`, `middleware.ts`, `postcss.config.mjs`, and `package.json`.  
> **Date:** 2026-04-28  
> **Severity legend:** 🔴 Critical (breaks core flow) | 🟠 High (user-visible regression) | 🟡 Medium (polish/DX) | ⚪ Warning (code smell / future risk)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Critical Issues — WebSocket Connection](#2-critical-issues--websocket-connection)
3. [Critical Issues — Evidence Page Blank Screen](#3-critical-issues--evidence-page-blank-screen)
4. [Auth & Session Flow Issues](#4-auth--session-flow-issues)
5. [Upload & Modal Flow Issues](#5-upload--modal-flow-issues)
6. [Agent Progress Display Issues](#6-agent-progress-display-issues)
7. [Analysis Decision Flow Issues](#7-analysis-decision-flow-issues)
8. [Result Page Issues](#8-result-page-issues)
9. [Config & Build Issues](#9-config--build-issues)
10. [Code Quality & Consistency Warnings](#10-code-quality--consistency-warnings)
11. [Prioritised Implementation Plan](#11-prioritised-implementation-plan)
12. [Complete Code Fixes](#12-complete-code-fixes)

---

## 1. Architecture Overview

The app is a Next.js 15 (App Router) frontend that:
- Proxies all `/api/v1/*` calls to a FastAPI backend via `src/app/api/v1/[...path]/route.ts`
- Authenticates via a Next.js Route Handler `/api/auth/demo` that calls the backend
- Communicates live analysis progress via a **direct browser WebSocket** (bypasses the Next.js proxy)
- Manages state in `useSimulation` (WS layer) and `useInvestigation` (orchestration)

---

## 2. Critical Issues — WebSocket Connection

### 🔴 ISSUE-WS-1 — Production CSP blocks WebSocket entirely

**File:** `src/middleware.ts`, line 7–9

**Problem:** In production, `connect-src` is set to `'self'` only. The WebSocket connects directly to the backend host (port 8000 or a different origin). The browser CSP engine blocks this connection silently — the WS `onerror` fires and the user sees "Failed to connect to stream" with no explanation.

```ts
// middleware.ts — CURRENT (BROKEN in production)
const connectSrc = isProd
  ? "'self'"   // ← blocks ws://api.yourdomain.com:8000 or wss://...
  : "'self' ws://localhost wss://localhost ...";
```

**Fix:** Add the WS backend URL to production `connect-src`. The backend origin must be read from `NEXT_PUBLIC_API_URL`:

```ts
// middleware.ts — FIXED
export function middleware(request: NextRequest) {
  const nonce = btoa(crypto.randomUUID()).replace(/=/g, "");

  const isProd = process.env.NODE_ENV === "production";
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "";

  // Derive WS origin from the API URL
  let wsOrigin = "";
  if (apiUrl) {
    try {
      const u = new URL(apiUrl);
      wsOrigin = `${u.protocol === "https:" ? "wss:" : "ws:"}//${u.host}`;
    } catch { /* ignore */ }
  }

  const connectSrc = isProd
    ? `'self' ${wsOrigin} ${apiUrl}`.trim()
    : "'self' ws://localhost wss://localhost ws://localhost:3000 wss://localhost:3000 ws://localhost:8000 wss://localhost:8000 http://localhost:8000 https://localhost:8000";

  const cspHeader = `
    default-src 'self';
    script-src 'self' 'nonce-${nonce}' 'strict-dynamic' ${!isProd ? "'unsafe-eval'" : ""};
    style-src 'self' 'unsafe-inline';
    img-src 'self' blob: data:;
    connect-src ${connectSrc};
    font-src 'self' data:;
    frame-ancestors 'none';
    form-action 'self';
  `.replace(/\s{2,}/g, " ").trim();

  // ... rest unchanged
}
```

---

### 🔴 ISSUE-WS-2 — `getWSBase()` falls back to `window.location.host` in production

**File:** `src/lib/api/utils.ts`, line 42–54

**Problem:** When `NEXT_PUBLIC_API_URL` is not set (or is set to the frontend URL like `https://app.domain.com`), the WebSocket is opened against the frontend host — but the backend WebSocket endpoint doesn't live there. The Next.js proxy does **not** handle WebSocket upgrades (Next.js App Router route handlers cannot proxy WS). This is silent — the WS fails after the 20s timeout.

```ts
// CURRENT — may build wrong WS URL
const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
return `${protocol}//${window.location.host}`; // ← points to Next.js, not backend
```

**Fix:** Add a runtime check that warns clearly, and ensure docs/env specify `NEXT_PUBLIC_API_URL` pointing to the **backend**:

```ts
// utils.ts — FIXED
export function getWSBase(): string {
  if (typeof window === "undefined") return "ws://backend:8000";

  if (RAW_API_BASE) {
    try {
      const url = new URL(RAW_API_BASE);
      const wsProto = url.protocol === "https:" ? "wss:" : "ws:";
      return `${wsProto}//${url.host}`;
    } catch { /* fall through */ }
  }

  // Dev convenience — Next.js on :3000, backend on :8000
  if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
    return `ws://${window.location.hostname}:8000`;
  }

  // Production fallback: same host (valid only if a WS-capable reverse proxy handles upgrades)
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  console.warn(
    "[FC] NEXT_PUBLIC_API_URL not set — WebSocket will connect to",
    `${protocol}//${window.location.host}. Ensure your reverse proxy forwards WS upgrades to the backend.`
  );
  return `${protocol}//${window.location.host}`;
}
```

---

### 🔴 ISSUE-WS-3 — Reconnect loop uses stale `sessionId` closure

**File:** `src/hooks/useSimulation.ts`, line ~340

**Problem:** Inside `handleClose`, the reconnect `setTimeout` captures `sessionId` (the React state variable). Because `connectWebSocket` is memoised with `[]` deps, `sessionId` is always `null` inside the callback. The reconnect falls back to `storage.getItem(SESSION_ID_KEY)` which works, but the stale state causes `setErrorMessage` to fire with the wrong message and the re-connection counter may reset incorrectly.

```ts
// CURRENT — sessionId is always null inside this closure
setTimeout(() => {
  const currentSessionId = sessionId || storage.getItem(SESSION_ID_KEY);
  //  ^ sessionId is null (stale closure) — storage fallback is always needed
  if (currentSessionId) {
    connectWebSocket(currentSessionId, true).catch(() => {});
  }
}, delay);
```

**Fix:** Always read from storage (remove `sessionId` from the expression to eliminate confusion):

```ts
// FIXED
setTimeout(() => {
  const currentSessionId = storage.getItem(SESSION_ID_KEY);
  if (currentSessionId) {
    connectWebSocket(currentSessionId, true).catch(() => {});
  }
}, delay);
```

---

### 🟠 ISSUE-WS-4 — `flushSync` called inside async `processQueue` 

**File:** `src/hooks/useSimulation.ts`, line 136

**Problem:** `flushSync` is imported dynamically then called inside an `async` function inside a `while` loop. Calling `flushSync` during an async task is dangerous: if React is already in the middle of a render (possible with React 18/19 concurrent mode), it throws. This can crash the entire WS message processing pipeline.

```ts
// CURRENT — risky
const { flushSync } = await import("react-dom");
flushSync(() => { /* setState calls */ });
```

**Fix:** Import `flushSync` at the top of the file (static import), and wrap each call in a try/catch:

```ts
// At top of file:
import { flushSync } from "react-dom";

// Inside processQueue:
try {
  flushSync(() => { /* setState calls */ });
} catch (e) {
  // flushSync not allowed in this render context; setState calls will batch normally
  /* setState calls here without flushSync */
}
```

---

### 🟠 ISSUE-WS-5 — `connectWebSocket` has empty deps array with `eslint-disable` suppression

**File:** `src/hooks/useSimulation.ts`, line 588

**Problem:** `connectWebSocket` is wrapped in `useCallback(fn, [])` with an `eslint-disable-next-line react-hooks/exhaustive-deps` comment. This means it never re-creates — which is intentional to avoid killing the socket, but also means it can never use updated state or props. Any bug introduced by this stale closure (see WS-3) is hard to trace. The comment also silences the linter entirely instead of using a more targeted suppression.

**Recommendation:** Document explicitly what refs are used in place of state, add a comment explaining the intent:

```ts
// connectWebSocket intentionally has empty deps.
// All state is accessed via refs (completedAgentsRef, playSoundRef, etc.)
// to avoid re-creating the socket on every state change.
// DO NOT add state dependencies here without thinking carefully.
// eslint-disable-next-line react-hooks/exhaustive-deps
}, []);
```

---

## 3. Critical Issues — Evidence Page Blank Screen

### 🔴 ISSUE-BLANK-1 — Three-way render deadlock leaves page empty

**File:** `src/app/evidence/page.tsx`, line 104–162

**Problem:** The evidence page has three mutually exclusive render conditions:

```
A) showUploadForm                         → renders FileUploadSection
B) hasStartedAnalysis && !showUploadForm  → renders AgentProgressDisplay
C) !showUploadForm && !hasStartedAnalysis → renders "Initializing..." fallback
```

On direct navigation to `/evidence` with an existing `forensic_session_id` in storage, the flow is:

1. Page mounts. `status = "idle"`, `isUploading = false`, `autoStartBlocking = false` → **condition C fires** briefly (blank-ish state visible)
2. `useLayoutEffect` reads `sessionOnlyStorage` — but `fc_show_loading` may not be set → `showLoadingOverlay = false`
3. The auto-reconnect `useEffect` fires, calls `startSimulation()` → `status = "initiating"` → `hasStartedAnalysis = true`... BUT it's async. There's a render between step 1 and step 3 where the page shows the fallback text.
4. If `connectWebSocket` fails (WS refused/backend down), `resetSimulation()` is called → `status = "idle"` → back to condition C → **permanent blank** with only the tiny "Initializing" text visible.

The user sees a blank page with only "Initializing the forensic workspace..." and an obscure "Reset loading & continue" button.

**Fix — Part 1:** Make `showUploadForm` show the upload form as the safe default when nothing is happening:

```ts
// useInvestigation.ts — FIXED
const showUploadForm =
  !autoStartBlocking &&
  status === "idle" &&
  !isUploading &&
  !wsConnectionError; // NEW: don't hide form if WS failed — show retry + upload form
```

**Fix — Part 2:** In evidence/page.tsx, show `FileUploadSection` when there's a WS error (with a retry banner), instead of falling through to the blank state:

```tsx
// evidence/page.tsx — FIXED render logic
{(showUploadForm || wsConnectionError) && !hasStartedAnalysis && (
  <>
    {wsConnectionError && (
      <div className="rounded-lg border border-red-500/30 bg-red-950/20 px-6 py-4 mb-6 text-sm text-red-300 flex items-center justify-between">
        <span>⚠ Connection failed: {wsConnectionError}</span>
        <button onClick={retryWsConnection} className="btn-pill-secondary text-xs px-4 py-1">
          Retry
        </button>
      </div>
    )}
    <FileUploadSection ... />
  </>
)}
```

---

### 🔴 ISSUE-BLANK-2 — Auto-reconnect fires on every `/evidence` navigation, even post-reset

**File:** `src/hooks/useInvestigation.ts`, line 361–390

**Problem:** When a user clicks "New Upload" from the evidence page (`handleNewUpload`), it calls `storage.removeItem("forensic_session_id")` then `router.push("/?upload=1")`. On the next visit to `/evidence`, `forensic_session_id` is gone, so the auto-reconnect block should not fire. **But** if the storage removal races with the router push (storage events are synchronous but Next.js router is async), it's possible the old session ID is still present when the `useEffect` runs on the fresh evidence page mount, triggering an unwanted reconnect.

**Fix:** Add an explicit "reconnect allowed" guard using a session-only flag:

```ts
// In handleNewUpload:
sessionOnlyStorage.setItem("fc_no_reconnect", "1");

// In the auto-reconnect useEffect:
const noReconnect = sessionOnlyStorage.getItem("fc_no_reconnect");
if (noReconnect) {
  sessionOnlyStorage.removeItem("fc_no_reconnect");
  return; // fresh upload — do not reconnect to old session
}
const existingSessionId = storage.getItem("forensic_session_id");
```

---

### 🟠 ISSUE-BLANK-3 — `autoStartBlocking` stuck at `true` causes permanent blank on back-navigation

**File:** `src/hooks/useInvestigation.ts`, line 117–127

**Problem:** `autoStartBlocking` is set to `true` from `sessionOnlyStorage("forensic_auto_start")` in a `useLayoutEffect`. If the user presses Back before the file analysis starts (auth pending or network slow), `autoStartFiredRef.current = false` still, and `autoStartBlocking = true`. This means `showUploadForm = false`, `hasStartedAnalysis = false` → blank page again.

**The safety guard at line 373–378 handles this**, but only when `status === "idle" && !isUploading`. During auth or WS setup, neither condition is true, leaving the user stuck for up to 20s.

**Fix:** Add an immediate reset on the `fc_show_loading` timeout path:

```ts
// In the autoStartBlocking safety guard, reduce from status===idle to also fire during error
} else if (!pending && autoStartBlocking && (status === "idle" || status === "error") && !isUploading) {
  setAutoStartBlocking(false);
  setShowLoadingOverlay(false);
  sessionOnlyStorage.removeItem("forensic_auto_start");
  sessionOnlyStorage.removeItem("fc_show_loading");
}
```

---

## 4. Auth & Session Flow Issues

### 🔴 ISSUE-AUTH-1 — `authReadyRef.current` rejection not caught in `triggerAnalysis`

**File:** `src/hooks/useInvestigation.ts`, line 238

**Problem:** `await authReadyRef.current` is inside a `try` block, but that `try` only wraps `startInvestigation`. If `authReadyRef.current` (a Promise set in a `useEffect`) rejects, the rejection bubbles up uncaught — the `finally` only resets `investigationInFlightRef` if `sessionIdToUse` is falsy. The `isUploading` state stays `true` forever and the UI is stuck.

**Fix:** *(Already documented in existing App Fixing.md — confirmed needed)*

```ts
// useInvestigation.ts — inside triggerAnalysis
try {
  await authReadyRef.current;
} catch (authErr) {
  setIsUploading(false);
  setShowLoadingOverlay(false);
  resetSimulation();
  investigationInFlightRef.current = false;
  toast.destructive({
    title: "Authentication failed",
    description: authErr instanceof Error ? authErr.message : "Could not establish session.",
  });
  return;
}
```

---

### 🟠 ISSUE-AUTH-2 — `isNavigating` never resets if user presses browser Back from `/evidence`

**File:** `src/components/ui/HeroAuthActions.tsx`

**Problem:** When `router.push("/evidence")` is called, `setIsNavigating(true)` stays `true` forever on that component. If the user presses Back (or navigation fails), returning to the landing page shows an infinite spinner overlay.

**Fix:** *(Already in `HeroAuthActions.tsx` line 68-70 — `useEffect(() => { setIsNavigating(false); }, [])` — CONFIRMED EXISTS, no action needed)*

---

### 🟠 ISSUE-AUTH-3 — Token stored in `sessionStorage` but checked in `localStorage`

**File:** `src/lib/api/utils.ts` vs `src/hooks/useInvestigation.ts`, line 169–175

**Problem:** `setAuthToken`/`getAuthToken` use `sessionStorage` directly. But `useInvestigation.ts` checks `storage.getItem("forensic_auth_ok")` where `storage = persistentStorage = localStorage`. These are different stores. A user who opens the app in a new tab shares `localStorage` state but not `sessionStorage`, so `forensic_auth_ok = "1"` in localStorage will prevent re-auth, but `getAuthToken()` from sessionStorage will return `null` — the check on line 171 is `forensic_auth_ok === "1" && getAuthToken() !== null`, which correctly requires both, but the logic is fragile and confusing.

**Recommendation:** Consolidate auth state. Either use `sessionStorage` everywhere or `localStorage` everywhere. Currently it's split:

```ts
// INCONSISTENT:
sessionStorage.setItem("forensic_auth_token", token);     // setAuthToken()
localStorage.setItem("forensic_auth_ok", "1");            // useInvestigation.ts
document.cookie includes "access_token"                   // checked in useInvestigation.ts
```

**Fix:** Remove the `forensic_auth_ok` localStorage key entirely. Instead rely solely on:
1. The HttpOnly cookie (`access_token`) set by `/api/auth/demo`
2. `getAuthToken()` from sessionStorage as a perf fast-path

```ts
// useInvestigation.ts — simplified auth check
if (document.cookie.includes("access_token") || getAuthToken() !== null) {
  authReadyRef.current = Promise.resolve();
} else {
  authReadyRef.current = autoLoginAsInvestigator().catch((err) => { ... });
}
```

---

## 5. Upload & Modal Flow Issues

### 🔴 ISSUE-MODAL-1 — UploadModal stays open after auth/health failure (stacked modals)

**File:** `src/components/ui/HeroAuthActions.tsx`, `handleStartAnalysis`

**Problem:** On the failure path (health check fails or auth throws), `setShowUpload(false)` is never called. Both the `UploadModal` and the `ForensicErrorModal` are mounted simultaneously, creating a broken double-modal UX.

**Fix:**

```ts
const handleStartAnalysis = useCallback(async () => {
  if (!selectedFile) return;
  setIsAuthenticating(true);
  setAuthError(null);

  try {
    const health = await checkBackendHealth();
    if (!health.ok) {
      setShowUpload(false);       // ← ADD
      setSelectedFile(null);      // ← ADD
      setIsAuthenticating(false);
      setAuthError(health.warmingUp ? "Protocol Warming Up… (60s)" : health.message);
      return;
    }
    await autoLoginAsInvestigator();
    storage.setItem("forensic_auth_ok", "1");
  } catch (err) {
    setShowUpload(false);         // ← ADD
    setSelectedFile(null);        // ← ADD
    setIsAuthenticating(false);
    setAuthError(err instanceof Error ? err.message : "Authentication failed");
    return;
  }

  setShowUpload(false);
  __pendingFileStore.file = selectedFile;
  sessionOnlyStorage.setItem("forensic_auto_start", "true");
  sessionOnlyStorage.setItem("fc_show_loading", "true");
  setIsNavigating(true);
  router.push("/evidence", { scroll: true });
  setIsAuthenticating(false);
}, [router, selectedFile]);
```

---

### 🟠 ISSUE-MODAL-2 — UploadModal backdrop click races file drop handler

**File:** `src/components/evidence/UploadModal.tsx`, line 56

**Problem:** `onClick={onClose}` on the backdrop fires when drag-and-drop events bubble up after a file drop, closing the modal immediately after selection.

**Fix:**

```tsx
// Replace onClick with onMouseDown + target check
<motion.div
  onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
  // Remove: onClick={onClose}
>
```

---

### 🟠 ISSUE-MODAL-3 — UploadSuccessModal has no close/ESC path

**File:** `src/components/evidence/UploadSuccessModal.tsx`

**Problem:** Users cannot dismiss the success modal with ESC or an X button — only "Reselect" or "Begin Analysis" work.

**Fix:**

```tsx
import { X } from "lucide-react";

// Inside modal header:
<button
  onClick={onNewUpload}
  aria-label="Close"
  data-testid="success-modal-close"
  className="absolute top-6 right-6 text-white/40 hover:text-primary transition-colors"
>
  <X className="w-5 h-5" />
</button>

// Add ESC handler:
useEffect(() => {
  const onEsc = (e: KeyboardEvent) => { if (e.key === "Escape") onNewUpload(); };
  window.addEventListener("keydown", onEsc);
  return () => window.removeEventListener("keydown", onEsc);
}, [onNewUpload]);
```

---

### 🟠 ISSUE-MODAL-4 — `crypto.randomUUID()` crashes on insecure HTTP context

**File:** `src/hooks/useInvestigation.ts`, line 233

**Problem:** `crypto.randomUUID()` is only available on HTTPS or localhost. On plain HTTP deployments (Docker dev without TLS), this throws `TypeError: crypto.randomUUID is not a function` and breaks the entire upload flow.

**Status:** A fallback already exists in the code:
```ts
const uuid = (typeof crypto !== "undefined" && "randomUUID" in crypto)
  ? crypto.randomUUID()
  : Math.random().toString(36).slice(2) + Date.now().toString(36);
```
✅ This is **already fixed in the current codebase** — no action needed.

---

## 6. Agent Progress Display Issues

### 🔴 ISSUE-AGENTS-1 — Decision buttons never appear if backend omits `PIPELINE_PAUSED`

**File:** `src/hooks/useInvestigation.ts`, line 525

**Problem:** Decision buttons require `awaitingDecision = true`. The primary path to set this is `status === "awaiting_decision"`, which is only set via the `PIPELINE_PAUSED` WebSocket message. If the WS disconnects after all agents complete but before `PIPELINE_PAUSED` is sent, or if the backend doesn't send it at all, `status` stays `"analyzing"` and no decision buttons appear — the user is stuck.

**Status:** The fallback condition already exists:
```ts
const awaitingDecision =
  status === "awaiting_decision" ||
  (phase === "initial" &&
   expectedAgentIds.size > 0 &&
   expectedCompletedCount >= expectedAgentIds.size &&
   !revealPending);
```
✅ **Already fixed** — but verify `expectedAgentIds` is never size 0 when MIME is known (see AGENTS-2 below).

---

### 🔴 ISSUE-AGENTS-2 — `expectedAgentIds` is size 0 when `mimeType` is null during hydration

**File:** `src/hooks/useInvestigation.ts`, line 503

**Problem:**

```ts
const [mimeType, setMimeType] = useState<string | null>(null);

useEffect(() => {
  setMimeType(storage.getItem("forensic_mime_type") || file?.type || null);
}, [file]);
```

On first render, `mimeType = null` → `supportedAgentIdsForMime(null)` returns an empty Set → `expectedAgentIds.size === 0` → `awaitingDecision` fallback condition `expectedAgentIds.size > 0` is false → **decision buttons never appear via fallback**.

The mimeType is only populated after the first `useEffect` runs (post-hydration). During that brief window, if all agents complete and `PIPELINE_PAUSED` wasn't received, buttons are permanently hidden.

**Fix:** Initialise `mimeType` synchronously:

```ts
const [mimeType, setMimeType] = useState<string | null>(() => {
  // Safe initialisation — storage is SSR-guarded internally
  return storage.getItem("forensic_mime_type") || null;
});

useEffect(() => {
  setMimeType(storage.getItem("forensic_mime_type") || file?.type || null);
}, [file]);
```

---

### 🔴 ISSUE-AGENTS-3 — `revealQueue` stall causes permanent "no decision buttons"

**File:** `src/hooks/useSimulation.ts`

**Problem:** Decision button visibility in `AgentProgressDisplay` requires `revealQueue.length === 0`. The sequential reveal pacing (400ms intervals) can stall if `isRevealingRef.current` gets stuck `true` — e.g., if the component unmounts mid-reveal or the `setRevealQueue` state update gets batched oddly.

**Status:** A watchdog exists that drains stuck items after 8s:
```ts
useEffect(() => {
  if (revealQueue.length === 0) return;
  const watchdog = setTimeout(() => { /* drain */ }, 8000);
  return () => clearTimeout(watchdog);
}, [revealQueue.length]);
```
✅ **Already fixed** — verify it clears `isRevealingRef.current = false` after drain (it does).

---

### 🟠 ISSUE-AGENTS-4 — Deep phase decision dock blocked by `awaitingDecision`

**File:** `src/components/evidence/AgentProgressDisplay.tsx`, bottom action dock

**Problem:** The deep-phase "View Report" dock renders when:
```tsx
{phase === "deep" && revealQueue.length === 0 && (allAgentsDone || pipelineStatus === "complete") && !arbiterDeliberating && ...}
```
This condition is correct. **But** if the backend emits a `PIPELINE_PAUSED` message even in deep phase (some pipeline configurations do this for HITL), `status = "awaiting_decision"` → the initial-phase dock attempts to show (condition: `awaitingDecision && phase === "initial"` — phase is `"deep"` so it won't). Neither dock shows. **Both conditions require different phases**. This is fine as-is, but confirm with backend that deep phase never emits `PIPELINE_PAUSED` without a HITL intent.

---

### 🟠 ISSUE-AGENTS-5 — Grid layout collapses when unsupported agents hide

**File:** `src/components/evidence/AgentProgressDisplay.tsx`, grid className

**Problem:** When 4/5 agents are unsupported (e.g., audio file with only Agent2 supported), the single remaining card renders in a 3-column grid, leaving an awkward 2/3 empty row.

**Fix:**

```tsx
<motion.div
  className={`grid gap-6 ${
    visibleAgents.length === 1 ? "grid-cols-1 max-w-xl mx-auto" :
    visibleAgents.length === 2 ? "grid-cols-1 md:grid-cols-2 max-w-2xl mx-auto" :
    "grid-cols-1 md:grid-cols-2 lg:grid-cols-3"
  }`}
  ...
>
```

---

### 🟠 ISSUE-AGENTS-6 — Deep phase grid empty on hard refresh mid-analysis

**File:** `src/components/evidence/AgentProgressDisplay.tsx`

**Problem:** On page refresh during deep phase, `forensic_initial_agents` may be absent if cleared by a prior reset. `supportedAgentIdsForMime` is the fallback, but if `mimeType` is also null at this point, `visibleAgents` is empty and the grid renders nothing.

**Fix:** Last-ditch fallback to all valid agents:

```ts
const initialAgentIds = useMemo<string[]>(() => {
  if (phase !== "deep") return [];
  const raw = storage.getItem<AgentUpdate[]>("forensic_initial_agents", true);
  if (Array.isArray(raw) && raw.length) return raw.map(a => a.agent_id).filter(Boolean);
  const fromMime = Array.from(supportedAgentIdsForMime(mimeType ?? undefined));
  if (fromMime.length) return fromMime;
  return allValidAgents.map(a => a.id); // ← last-ditch fallback
}, [phase, mimeType]);
```

---

### 🟡 ISSUE-AGENTS-7 — `degraded: true` findings have no visual indicator

**File:** `src/components/evidence/AgentStatusCard.tsx`

**Problem:** The `AgentUpdate` type has `degraded?: boolean` and `fallback_reason?: string`, but no badge or visual is rendered when a finding is degraded. Investigators need to know when a tool fell back to a less reliable method.

**Fix:** In `AgentStatusCard.tsx`, when rendering a finding:

```tsx
{finding.degraded && (
  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-amber-500/10 text-amber-400 border border-amber-500/20 font-mono">
    ⚠ Fallback{finding.fallback_reason ? `: ${finding.fallback_reason}` : ""}
  </span>
)}
```

---

### 🟡 ISSUE-AGENTS-8 — Accept Verdict button missing spinner during navigation

**File:** `src/components/evidence/AgentProgressDisplay.tsx`, line ~295

**Problem:** The "Accept Verdict" button disables during navigation but shows no spinner — user may click again thinking it didn't register.

**Fix:**

```tsx
<button
  data-testid="accept-analysis-btn"
  onClick={onAcceptAnalysis}
  disabled={isNavigating}
  className="flex-1 btn-horizon-outline py-3 text-xs flex items-center justify-center gap-2"
>
  {isNavigating ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
  <span>Accept Verdict</span>
</button>
```

---

### 🟡 ISSUE-AGENTS-9 — Mobile bottom dock overlaps last agent card

**File:** `src/components/evidence/AgentProgressDisplay.tsx`

**Problem:** `fixed bottom-12` dock overlaps the last card on small screens.

**Fix:** Add bottom padding to the grid container:

```tsx
<div className="flex flex-col w-full max-w-[1560px] mx-auto gap-8 pb-48 pt-24">
```

---

## 7. Analysis Decision Flow Issues

### 🔴 ISSUE-FLOW-1 — `handleAcceptAnalysis` silently swallows errors, routes on timeout

**File:** `src/hooks/useInvestigation.ts`, `handleAcceptAnalysis`

**Status:** Already correctly implemented in the current code with proper `catch` block showing toast. **Also** the `waitForFinalReport` return value `ok` is checked:
```ts
const ok = await waitForFinalReport(...);
if (!ok) throw new Error("Council synthesis timed out");
router.push("/result", { scroll: true });
```
✅ **Already fixed** — no action needed.

---

### 🔴 ISSUE-FLOW-2 — Background arbiter polling continues after "New Upload"

**File:** `src/hooks/useInvestigation.ts`, `handleNewUpload`

**Status:** `arbiterAbortControllerRef.current?.abort()` is called in `handleNewUpload`:
```ts
const handleNewUpload = useCallback(() => {
  playSound("click");
  arbiterAbortControllerRef.current?.abort();
  arbiterAbortControllerRef.current = null;
  ...
```
✅ **Already fixed** — verified.

---

### 🟠 ISSUE-FLOW-3 — `arbiterLiveText` not cleared between sessions

**File:** `src/hooks/useInvestigation.ts`, `triggerAnalysis`

**Problem:** If user accepts analysis, sees live council text, goes back and uploads again, the old `arbiterLiveText` is briefly visible before being cleared.

**Fix:** Add to the start of `triggerAnalysis`:

```ts
setArbiterLiveText("");  // ← already exists at line ~226 — ✅ confirmed present
```

✅ **Already fixed**.

---

### 🟠 ISSUE-FLOW-4 — `handleDeepAnalysis` button not disabled immediately on click

**File:** `src/components/evidence/AgentProgressDisplay.tsx`

**Problem:** The "Deep Analysis" button has `disabled={isNavigating || (phase as string) === "deep"}` but `isNavigating` is only set when navigating to `/result`, not when starting deep analysis. A rapid double-click can start two deep analysis requests.

**Fix:** The `investigationInFlightRef.current` guard in `handleDeepAnalysis` handles this at the logic level. But add visual feedback:

```tsx
// In AgentProgressDisplay, use a local submitting state or pass `isDeepLoading` prop
// Alternatively, disable based on phase change which is synchronous:
disabled={isNavigating || phase === "deep"}
// phase changes synchronously via setPhase in handleDeepAnalysis ✅ — already correct
```

---

## 8. Result Page Issues

### 🟠 ISSUE-RESULT-1 — `persistentStorage` used in `useResult` but `storage = persistentStorage`

**File:** `src/hooks/useResult.ts`, line 16 + 32

**Problem:** Both `storage` and `persistentStorage` are imported, but `storage` is an alias for `persistentStorage` (`export const storage = persistentStorage`). Using both names is confusing and error-prone.

**Fix:** Remove the `persistentStorage` import and use only `storage`:

```ts
// BEFORE:
import { storage, persistentStorage } from "@/lib/storage";
const getInitial = (key: string) => persistentStorage.getItem(key);

// AFTER:
import { storage } from "@/lib/storage";
const getInitial = (key: string) => storage.getItem(key);
```

---

### 🟠 ISSUE-RESULT-2 — Result page shows "Council deliberating" forever if `sessionId` is null on mount

**File:** `src/hooks/useResult.ts`, line 91–93

**Problem:** `sessionId` is initialised as:
```ts
const [sessionId, setSessionId] = useState<string | null>(() =>
  typeof window !== "undefined" ? storage.getItem("forensic_session_id") : null
);
```

On SSR (the first render on server), `typeof window === "undefined"` so `sessionId = null`. The arbiter polling `useEffect` runs after mount (client-side), but `mounted` flag gates it. This is correct. However, if `forensic_session_id` was removed (e.g., by handleNew) before navigation completes, `sessionId = null` → `setState("empty")`. The "empty" state should show a helpful redirect prompt, not just an empty div.

**Check:** Verify that the `ResultStateView` component renders a "No analysis found — Go Home" UI for `state === "empty"`. If not:

```tsx
// In ResultStateView or ResultLayout:
{state === "empty" && (
  <div className="flex flex-col items-center gap-6 py-20">
    <p className="text-foreground/60">No analysis found.</p>
    <button onClick={handleHome} className="btn-horizon-outline px-8 py-3">
      Return Home
    </button>
  </div>
)}
```

---

### 🟡 ISSUE-RESULT-3 — Report export uses `report.report_id.slice(0, 8)` — may be undefined

**File:** `src/hooks/useResult.ts`, `handleExport`

**Problem:** If `report.report_id` is `undefined` (schema evolution / backend change), `.slice(0, 8)` throws.

**Fix:**

```ts
a.download = `forensic-report-${(report.report_id ?? "unknown").slice(0, 8)}.json`;
```

---

## 9. Config & Build Issues

### 🟠 ISSUE-CONFIG-1 — `getCspNonce` defined but never used in `layout.tsx`

**File:** `src/app/layout.tsx`, line 40–43

**Problem:** The CSP nonce is generated in `middleware.ts` and passed as a header `x-nonce`. `getCspNonce()` reads it in the layout — but the nonce value is never passed to any `<script>` tag, `<style>` tag, or injected into the page. The entire nonce mechanism is wired up but not actually applied.

**Fix Option A (Simple):** Remove `getCspNonce` and the nonce-based CSP from middleware — use the existing header-based CSP without nonce (current approach effectively already does this since nonce isn't applied to any tag).

**Fix Option B (Complete):** Actually use the nonce:

```tsx
// layout.tsx
export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const nonce = await getCspNonce();
  return (
    <html ...>
      <head>
        {/* Pass nonce to Next.js's script injection */}
        <meta name="csp-nonce" content={nonce} />
      </head>
      <body ...>
```

And in `next.config.ts`:
```ts
experimental: {
  nonce: true, // Enable Next.js nonce injection
}
```

---

### 🟠 ISSUE-CONFIG-2 — `ignoreBuildErrors: true` and `ignoreDuringBuilds: true` mask real problems

**File:** `apps/web/next.config.ts`, lines 44–49

```ts
eslint: { ignoreDuringBuilds: true },
typescript: { ignoreBuildErrors: true },
```

**Problem:** These flags hide TypeScript and ESLint errors during builds, meaning broken code ships to production silently. Given the number of `any` casts and suppressed lint rules found in this codebase, this is a significant risk.

**Recommendation:** Remove both flags and fix the underlying TS/lint errors progressively. At minimum, run `tsc --noEmit` and `eslint src` in CI before every merge. (The CI workflow exists — verify these commands run in `.github/workflows/ci.yml`.)

---

### 🟡 ISSUE-CONFIG-3 — `lib/api.ts` is an 8-line shim that duplicates `lib/api/index.ts` exports

**File:** `src/lib/api.ts`

**Problem:** `lib/api.ts` only re-exports everything from `lib/api/index`. This creates a redundant module resolution path. Both `@/lib/api` and `@/lib/api/index` resolve to the same exports, causing potential confusion about which path to import from (some files use one, some use the other).

**Fix:** Remove `lib/api.ts` and update all imports to use `@/lib/api/client`, `@/lib/api/utils`, or `@/lib/api/index` directly. Or keep the shim but add a note explaining it's the canonical import path.

---

### 🟡 ISSUE-CONFIG-4 — `backendTargets.ts` is a server-only file imported in Route Handler only

**File:** `src/lib/backendTargets.ts`

**Problem:** This file uses `process.env` directly (no `NEXT_PUBLIC_` prefix) — it's server-only. But it's also imported by `src/lib/api.ts` which is itself imported by client components. Next.js will either tree-shake it correctly or it will leak server env vars to the client bundle.

**Fix:** Add `"server-only"` guard:

```ts
// backendTargets.ts — top of file
import "server-only";  // Throws at build time if bundled for client
```

---

### ⚪ ISSUE-CONFIG-5 — `outputFileTracingRoot` path may break in monorepo CI

**File:** `apps/web/next.config.ts`, line 23

```ts
outputFileTracingRoot: path.join(__dirname, "../../"),
```

This points to the monorepo root, which is correct for `output: "standalone"` to include shared packages. Verify this path is correct relative to `apps/web/`. In the current structure: `apps/web/` → `../../` = root. ✅ Correct.

---

## 10. Code Quality & Consistency Warnings

### ⚪ WARN-1 — `revealQueue` and `revealPending` both exported from `useSimulation`

**File:** `src/hooks/useSimulation.ts` return value

`revealPending: revealQueue.length > 0` is derived from `revealQueue`, so both convey the same signal. Consumers use `revealQueue` for its length check and `revealPending` as a boolean gate. This is fine but redundant. Pick one as the public API surface and remove the other to stop drift.

---

### ⚪ WARN-2 — Magic string keys for storage scattered across files

Keys like `"forensic_session_id"`, `"forensic_mime_type"`, etc., are defined as constants in some places (`useSimulation.ts`: `const SESSION_ID_KEY = "forensic_session_id"`) but used as raw strings in others (`evidence/page.tsx`: `const FORENSIC_SESSION_ID_KEY = "forensic_session_id"`). 

**Fix:** Create `src/lib/storageKeys.ts`:

```ts
export const STORAGE_KEYS = {
  SESSION_ID: "forensic_session_id",
  MIME_TYPE: "forensic_mime_type",
  FILE_NAME: "forensic_file_name",
  CASE_ID: "forensic_case_id",
  INVESTIGATOR_ID: "forensic_investigator_id",
  THUMBNAIL: "forensic_thumbnail",
  PIPELINE_START: "forensic_pipeline_start",
  IS_DEEP: "forensic_is_deep",
  INITIAL_AGENTS: "forensic_initial_agents",
  DEEP_AGENTS: "forensic_deep_agents",
  AUTH_OK: "forensic_auth_ok",
  HITL_CHECKPOINT: "forensic_hitl_checkpoint",
  INVESTIGATION_CTX: "forensic_investigation_ctx",
} as const;
```

---

### ⚪ WARN-3 — `useForensicData` imported in `useResult` but its purpose is unclear

**File:** `src/hooks/useResult.ts`, line 38

`useForensicData()` is called but its return value is discarded. The hook likely has side effects (hydrating state from storage). This pattern is opaque and makes it hard to understand what `useResult` depends on.

**Fix:** Either export a named effect from `useForensicData` that makes the side-effect explicit, or inline the logic into `useResult`.

---

### ⚪ WARN-4 — `layout.tsx` defines `getCspNonce` as `async` Server Action pattern but doesn't `await` it

**File:** `src/app/layout.tsx`, line 40

`getCspNonce()` is `async` but the `RootLayout` function is also `async` only because of this call — yet the result `nonce` is never used anywhere in the returned JSX. The unused `async` adds overhead to every render.

**Fix:** Remove `getCspNonce()` call and the function entirely until nonce support is fully implemented.

---

## 11. Prioritised Implementation Plan

### Phase 1 — Critical: Fix WebSocket & Blank Screen (Day 1)

| # | Issue | File | Est |
|---|-------|------|-----|
| 1 | ISSUE-WS-1: CSP blocks WS in production | `middleware.ts` | 15 min |
| 2 | ISSUE-WS-2: getWSBase fallback | `lib/api/utils.ts` | 10 min |
| 3 | ISSUE-BLANK-1: Evidence page three-way deadlock | `app/evidence/page.tsx` + `useInvestigation.ts` | 30 min |
| 4 | ISSUE-BLANK-2: Auto-reconnect on fresh upload | `useInvestigation.ts` | 15 min |
| 5 | ISSUE-AUTH-1: authReadyRef rejection not caught | `useInvestigation.ts` | 10 min |
| 6 | ISSUE-WS-3: Stale sessionId in reconnect | `useSimulation.ts` | 5 min |
| 7 | ISSUE-WS-4: flushSync in async context | `useSimulation.ts` | 20 min |

**Total Phase 1: ~1h 45min**

---

### Phase 2 — High: Fix Modals & Agent UX (Day 1–2)

| # | Issue | File | Est |
|---|-------|------|-----|
| 8 | ISSUE-MODAL-1: Double modal on auth failure | `HeroAuthActions.tsx` | 15 min |
| 9 | ISSUE-MODAL-2: Backdrop click race | `UploadModal.tsx` | 5 min |
| 10 | ISSUE-MODAL-3: No ESC/close on success modal | `UploadSuccessModal.tsx` | 10 min |
| 11 | ISSUE-AGENTS-2: mimeType null on hydration | `useInvestigation.ts` | 10 min |
| 12 | ISSUE-AGENTS-5: Grid layout collapse | `AgentProgressDisplay.tsx` | 10 min |
| 13 | ISSUE-AGENTS-6: Deep phase empty grid on refresh | `AgentProgressDisplay.tsx` | 15 min |
| 14 | ISSUE-AGENTS-8: Accept button spinner | `AgentProgressDisplay.tsx` | 5 min |
| 15 | ISSUE-AGENTS-9: Mobile dock overlap | `AgentProgressDisplay.tsx` | 5 min |
| 16 | ISSUE-BLANK-3: autoStartBlocking stuck in error | `useInvestigation.ts` | 10 min |

**Total Phase 2: ~1h 25min**

---

### Phase 3 — Medium: Polish & Config (Day 2–3)

| # | Issue | File | Est |
|---|-------|------|-----|
| 17 | ISSUE-CONFIG-1: getCspNonce unused | `layout.tsx` | 5 min |
| 18 | ISSUE-CONFIG-2: ignoreBuildErrors | `next.config.ts` | 5 min + fix time |
| 19 | ISSUE-CONFIG-4: backendTargets server-only | `backendTargets.ts` | 5 min |
| 20 | ISSUE-RESULT-1: persistentStorage alias | `useResult.ts` | 5 min |
| 21 | ISSUE-RESULT-3: report_id undefined | `useResult.ts` | 5 min |
| 22 | ISSUE-AGENTS-7: Degraded findings badge | `AgentStatusCard.tsx` | 20 min |
| 23 | WARN-2: Storage key constants | new `storageKeys.ts` | 30 min |
| 24 | ISSUE-AUTH-3: Auth state consolidation | `useInvestigation.ts` | 20 min |

**Total Phase 3: ~1h 35min**

---

## 12. Complete Code Fixes

### Fix 1: `middleware.ts` — CSP WebSocket in Production

```typescript
// src/middleware.ts — COMPLETE FILE
import { NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest) {
  const nonce = btoa(crypto.randomUUID()).replace(/=/g, "");

  const isProd = process.env.NODE_ENV === "production";
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "";

  // Derive WS origin from NEXT_PUBLIC_API_URL
  let wsOrigin = "";
  let httpOrigin = "";
  if (apiUrl) {
    try {
      const u = new URL(apiUrl);
      wsOrigin = `${u.protocol === "https:" ? "wss:" : "ws:"}//${u.host}`;
      httpOrigin = `${u.protocol}//${u.host}`;
    } catch { /* ignore */ }
  }

  const prodConnectSrc = `'self' ${wsOrigin} ${httpOrigin}`.trim().replace(/\s+/g, " ");
  const devConnectSrc = "'self' ws://localhost wss://localhost ws://localhost:3000 wss://localhost:3000 ws://localhost:8000 wss://localhost:8000 http://localhost:8000 https://localhost:8000";
  
  const connectSrc = isProd ? prodConnectSrc : devConnectSrc;

  const cspHeader = `
    default-src 'self';
    script-src 'self' 'nonce-${nonce}' 'strict-dynamic' ${!isProd ? "'unsafe-eval'" : ""};
    style-src 'self' 'unsafe-inline';
    img-src 'self' blob: data:;
    connect-src ${connectSrc};
    font-src 'self' data:;
    frame-ancestors 'none';
    form-action 'self';
  `.replace(/\s{2,}/g, " ").trim();

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", cspHeader);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", cspHeader);
  return response;
}

export const config = {
  matcher: [
    {
      source: "/((?!api|_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
```

---

### Fix 2: `useSimulation.ts` — flushSync Import & Stale SessionId

```typescript
// At top of file — add static import:
import { flushSync } from "react-dom";

// In handleClose reconnect setTimeout — replace stale sessionId:
setTimeout(() => {
  const currentSessionId = storage.getItem(SESSION_ID_KEY);
  if (currentSessionId) {
    connectWebSocket(currentSessionId, true).catch(() => {});
  }
}, delay);

// In processQueue — wrap flushSync calls:
// REPLACE: const { flushSync } = await import("react-dom");
// REPLACE: flushSync(() => { ... });
// WITH:
try {
  flushSync(() => {
    switch (update.type) {
      // ... all cases unchanged
    }
  });
} catch {
  // React is already rendering — setState will batch normally
  // Apply updates without flushSync as fallback
  switch (update.type) {
    // ... same cases without flushSync
  }
}
```

---

### Fix 3: `useInvestigation.ts` — mimeType Sync Init + Auth Error + Auto-reconnect Guard

```typescript
// 1. Synchronous mimeType initialisation (line ~495):
const [mimeType, setMimeType] = useState<string | null>(() =>
  storage.getItem("forensic_mime_type") || null
);

useEffect(() => {
  setMimeType(storage.getItem("forensic_mime_type") || file?.type || null);
}, [file]);

// 2. authReadyRef.current catch block (add BEFORE startInvestigation try block):
try {
  await authReadyRef.current;
} catch (authErr) {
  setIsUploading(false);
  setShowLoadingOverlay(false);
  resetSimulation();
  investigationInFlightRef.current = false;
  toast.destructive({
    title: "Authentication failed",
    description: authErr instanceof Error ? authErr.message : "Could not establish session.",
  });
  return;
}

// 3. No-reconnect guard in handleNewUpload (before router.push):
sessionOnlyStorage.setItem("fc_no_reconnect", "1");

// 4. In the auto-reconnect useEffect — add guard at top:
const noReconnect = sessionOnlyStorage.getItem("fc_no_reconnect");
if (noReconnect) {
  sessionOnlyStorage.removeItem("fc_no_reconnect");
  // Don't reconnect to old session — fresh upload requested
} else {
  const existingSessionId = storage.getItem("forensic_session_id");
  if (existingSessionId) {
    // ... existing auto-reconnect logic
  }
}

// 5. autoStartBlocking safety guard — also fire on "error" status:
} else if (!pending && autoStartBlocking && (status === "idle" || status === "error") && !isUploading) {
  setAutoStartBlocking(false);
  setShowLoadingOverlay(false);
  sessionOnlyStorage.removeItem("forensic_auto_start");
  sessionOnlyStorage.removeItem("fc_show_loading");
}
```

---

### Fix 4: `app/evidence/page.tsx` — Eliminate Blank Screen

```tsx
// evidence/page.tsx — Replace the conditional render section:

<main className="max-w-[1560px] mx-auto relative z-10 w-full">
  <PageTransition>
    <>
      {/* Show upload form when idle OR when WS failed (with error banner) */}
      {(showUploadForm || (wsConnectionError && !hasStartedAnalysis)) && (
        <>
          {wsConnectionError && (
            <div className="mb-6 rounded-lg border border-red-500/30 bg-red-950/20 px-6 py-4 text-sm text-red-300 flex items-center justify-between gap-4">
              <span>⚠ Stream connection failed: {wsConnectionError}</span>
              <button
                onClick={retryWsConnection}
                className="btn-pill-secondary text-xs px-4 py-1 shrink-0"
              >
                Retry Connection
              </button>
            </div>
          )}
          <FileUploadSection
            key="upload-form"
            file={file}
            isDragging={isDragging}
            isUploading={isUploading}
            validationError={validationError}
            onFileSelect={handleFile}
            onFileDrop={handleFile}
            onDragEnter={() => setIsDragging(true)}
            onDragLeave={() => setIsDragging(false)}
            onUpload={triggerAnalysis}
            onClear={() => { setFile(null); setValidationError(null); }}
          />
        </>
      )}

      {hasStartedAnalysis && !showUploadForm && (
        <AgentProgressDisplay key="agent-progress" ... />
      )}

      {/* Fallback — only shows during the brief initiating window */}
      {!showUploadForm && !hasStartedAnalysis && !showLoadingOverlay && !wsConnectionError && (
        <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4 text-center px-6">
          <div className="w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
          <p className="text-sm text-foreground/55 max-w-md">
            Initializing the forensic workspace...
          </p>
          <button
            type="button"
            onClick={() => {
              setAutoStartBlocking(false);
              setShowLoadingOverlay(false);
              sessionOnlyStorage.removeItem(FC_SHOW_LOADING_KEY);
              sessionOnlyStorage.removeItem(FORENSIC_AUTO_START_KEY);
            }}
            className="btn-pill-secondary px-6 py-2 text-xs"
          >
            Reset & Upload New File
          </button>
        </div>
      )}
    </>
  </PageTransition>
</main>
```

---

### Fix 5: `HeroAuthActions.tsx` — Close Modal on Auth Failure

```tsx
// In handleStartAnalysis — add setShowUpload(false) on both failure paths:
const handleStartAnalysis = useCallback(async () => {
  if (!selectedFile || isAuthenticating || isNavigating) return;
  setIsAuthenticating(true);
  setAuthError(null);

  try {
    const health = await checkBackendHealth();
    if (!health.ok) {
      setShowUpload(false);        // ← ADD
      setSelectedFile(null);       // ← ADD
      setIsAuthenticating(false);
      setAuthError(health.warmingUp
        ? "Protocol Warming Up... Please wait ~60s and try again."
        : health.message
      );
      return;
    }
    await autoLoginAsInvestigator();
    storage.setItem("forensic_auth_ok", "1");
  } catch (err) {
    setShowUpload(false);          // ← ADD
    setSelectedFile(null);         // ← ADD
    setIsAuthenticating(false);
    if (err instanceof ProtocolWarmingError) {
      setAuthError("Protocol Warming Up... Retrying automatically.");
    } else {
      setAuthError(err instanceof Error ? err.message : "Authentication failed");
    }
    return;
  }

  setShowUpload(false);
  __pendingFileStore.file = selectedFile;
  sessionOnlyStorage.setItem("forensic_auto_start", "true");
  sessionOnlyStorage.setItem("fc_show_loading", "true");
  setIsNavigating(true);
  router.push("/evidence", { scroll: true });
  setIsAuthenticating(false);
}, [router, selectedFile, isAuthenticating, isNavigating]);
```

---

### Fix 6: `UploadModal.tsx` — Prevent Backdrop Closing on Drop

```tsx
// Replace onClick={onClose} on the backdrop div with:
<motion.div
  // ... existing props
  onMouseDown={(e) => {
    if (e.target === e.currentTarget) onClose();
  }}
  // REMOVE: onClick={onClose}
>
```

---

### Fix 7: `AgentProgressDisplay.tsx` — Grid Layout + Accept Spinner + Padding

```tsx
// 1. Responsive grid:
<motion.div
  className={`grid gap-6 ${
    visibleAgents.length === 1
      ? "grid-cols-1 max-w-xl mx-auto"
      : visibleAgents.length === 2
      ? "grid-cols-1 md:grid-cols-2 max-w-2xl mx-auto"
      : "grid-cols-1 md:grid-cols-2 lg:grid-cols-3"
  }`}
  variants={containerVariants}
  initial="hidden"
  animate="show"
>

// 2. Bottom padding on container div:
<div className="flex flex-col w-full max-w-[1560px] mx-auto gap-8 pb-48 pt-24">

// 3. Accept Verdict button spinner:
<button
  data-testid="accept-analysis-btn"
  onClick={onAcceptAnalysis}
  disabled={isNavigating}
  className="flex-1 btn-horizon-outline py-3 text-xs flex items-center justify-center gap-2"
>
  {isNavigating && <Loader2 className="w-4 h-4 animate-spin" />}
  <span>Accept Verdict</span>
</button>

// 4. Deep phase grid fallback (add to initialAgentIds useMemo):
const initialAgentIds = useMemo<string[]>(() => {
  if (phase !== "deep") return [];
  const raw = storage.getItem<AgentUpdate[]>("forensic_initial_agents", true);
  if (Array.isArray(raw) && raw.length) {
    return raw.map((a) => a.agent_id).filter((id): id is string => typeof id === "string");
  }
  const fromMime = Array.from(supportedAgentIdsForMime(mimeType || undefined));
  if (fromMime.length) return fromMime;
  return allValidAgents.map(a => a.id); // Last-ditch: never show empty grid
}, [phase, mimeType]);
```

---

### Fix 8: `useResult.ts` — Cleanup

```typescript
// Remove persistentStorage import alias:
import { storage } from "@/lib/storage";  // Remove persistentStorage

// Use storage everywhere:
const getInitial = (key: string) => storage.getItem(key);

// Safe report_id in export:
a.download = `forensic-report-${(report.report_id ?? "unknown").slice(0, 8)}.json`;
```

---

### Fix 9: `backendTargets.ts` — Mark as Server-Only

```typescript
// src/lib/backendTargets.ts — add at top:
import "server-only";

function normalizeBaseUrl(url: string): string {
  // ... unchanged
```

---

### Fix 10: `layout.tsx` — Remove Unused Nonce

```tsx
// Remove this unused function:
// async function getCspNonce() { ... }

// Remove the async keyword from RootLayout since getCspNonce is gone:
export default function RootLayout({ children }: { children: React.ReactNode }) {
  // No async needed
  return (
    <html ...>
```

---

## Summary Priority Matrix

| Priority | Count | Description |
|----------|-------|-------------|
| 🔴 Critical | 7 | Break core user flow (WS connection, blank screen, auth) |
| 🟠 High | 9 | User-visible regressions (modals, agent grid, mobile layout) |
| 🟡 Medium | 4 | Polish & DX improvements |
| ⚪ Warnings | 5 | Code quality, maintainability |

**Estimated total fix time: ~5 hours of focused work**

Implement in order: Phase 1 → Phase 2 → Phase 3. After Phase 1, the WebSocket connection and blank screen issues will be resolved. After Phase 2, the full upload-to-result flow will be reliable. Phase 3 improves maintainability and production safety.
